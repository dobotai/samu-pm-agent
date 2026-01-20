#!/usr/bin/env python3
"""
Client Status & Sentiment Report Tool
Generates comprehensive report combining Airtable video statuses with Slack client channel sentiment

Features:
1. Video status summary per client (from Airtable)
2. Client sentiment analysis (from Slack messages)
3. Response time tracking
4. Risk indicators (frustrated clients, delayed projects)

Usage:
    python client_status_report.py [--hours <num>] [--client <name>] [--output <format>]

Examples:
    python client_status_report.py --hours 72
    python client_status_report.py --client "Josh" --hours 168
    python client_status_report.py --output json
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime, timedelta
from collections import defaultdict
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from pyairtable import Api
from dotenv import load_dotenv

load_dotenv()

# Airtable constants for building URLs
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID', 'apph2RxHbsyqmCwxk')
AIRTABLE_TABLE_IDS = {
    'Videos': 'tblNurSDTg4BKwbWZ',
    'Clients': 'tblk4TsVaQh75Qn9R',
    'Team': 'tblw0Wk7GvbLyKv5m',
}


def get_airtable_record_url(table_name, record_id):
    """Generate a clickable Airtable URL for a record"""
    table_id = AIRTABLE_TABLE_IDS.get(table_name, '')
    if table_id and record_id:
        return f"https://airtable.com/{AIRTABLE_BASE_ID}/{table_id}/{record_id}"
    return None


# Sentiment keywords
POSITIVE_KEYWORDS = [
    'great', 'awesome', 'perfect', 'love', 'excellent', 'amazing', 'fantastic',
    'thank', 'thanks', 'appreciate', 'happy', 'pleased', 'wonderful', 'brilliant',
    'good job', 'well done', 'nice', 'excited', 'impressive'
]

NEGATIVE_KEYWORDS = [
    'disappointed', 'frustrat', 'upset', 'unhappy', 'wrong', 'issue', 'problem',
    'delay', 'late', 'waiting', 'where', 'when', 'still', 'yet', 'concern',
    'not happy', 'confused', 'unclear', 'mistake', 'error', 'fix', 'redo',
    'urgent', 'asap', 'immediately', 'overdue'
]

QUESTION_PATTERNS = [
    r'\?$', r'when will', r'where is', r'what about', r'any update',
    r'status', r'eta', r'how long', r'can you'
]

# Messages that are just acknowledgments (don't need a response)
ACKNOWLEDGMENT_PATTERNS = [
    r'^(ok|okay|k|kk)[\.\!]?$',
    r'^(thanks|thank you|thx|ty)[\.\!]?$',
    r'^(awesome|great|perfect|nice|cool|sounds good|got it|noted)[\.\!]?$',
    r'^(yes|yep|yup|yeah|yea)[\.\!]?$',
    r'^(no problem|np|no worries|nw)[\.\!]?$',
    r'^\:[\w\+\-]+\:$',  # Just an emoji reaction
    r'^(will do|on it|doing it now)[\.\!]?$',
]


def is_acknowledgment(text):
    """Check if message is just an acknowledgment that doesn't need response"""
    text_lower = text.lower().strip()
    # Very short messages that are just reactions
    if len(text_lower) < 15:
        for pattern in ACKNOWLEDGMENT_PATTERNS:
            if re.match(pattern, text_lower, re.IGNORECASE):
                return True
    return False


def needs_response(text):
    """Check if a message actually needs a response"""
    if is_acknowledgment(text):
        return False

    text_lower = text.lower()

    # Questions need responses
    if '?' in text:
        return True

    # Requests/asks need responses
    request_patterns = [
        r'can you', r'could you', r'please', r'need', r'want',
        r'when will', r'where is', r'what about', r'any update',
        r'let me know', r'waiting for', r'status on'
    ]
    for pattern in request_patterns:
        if pattern in text_lower:
            return True

    # Longer substantive messages likely need responses
    if len(text) > 100:
        return True

    return False


def get_team_slack_ids():
    """Get Slack IDs for all team members from Airtable"""
    api_key = os.getenv('AIRTABLE_API_KEY')
    base_id = os.getenv('AIRTABLE_BASE_ID', 'apph2RxHbsyqmCwxk')

    if not api_key:
        return set()

    try:
        api = Api(api_key)
        team_table = api.table(base_id, 'Team')
        team = team_table.all()

        slack_ids = set()
        for member in team:
            slack_id = member['fields'].get('Slack ID', '')
            if slack_id:
                slack_ids.add(slack_id)

        # Also add known admin/manager IDs (Samu, etc.)
        # These might not be in the Team table but are internal
        slack_ids.add('U070CUSP75M')  # Samu (commonly seen in channels)

        return slack_ids
    except:
        return set()


def get_airtable_data():
    """Fetch videos and clients from Airtable"""
    api_key = os.getenv('AIRTABLE_API_KEY')
    base_id = os.getenv('AIRTABLE_BASE_ID', 'apph2RxHbsyqmCwxk')

    if not api_key:
        raise ValueError("AIRTABLE_API_KEY not found")

    api = Api(api_key)

    videos_table = api.table(base_id, 'Videos')
    videos = videos_table.all()

    clients_table = api.table(base_id, 'Clients')
    clients = clients_table.all()

    return videos, clients


def get_slack_client():
    """Initialize Slack client"""
    token = os.getenv('SLACK_USER_TOKEN') or os.getenv('SLACK_BOT_TOKEN')
    if not token:
        raise ValueError("SLACK_USER_TOKEN or SLACK_BOT_TOKEN not found")
    return WebClient(token=token)


def get_client_channels(slack_client):
    """Get all client channels"""
    try:
        response = slack_client.conversations_list(
            types='public_channel,private_channel',
            limit=1000
        )
        channels = response.get('channels', [])
        # Filter for client channels
        client_channels = [
            ch for ch in channels
            if '-client' in ch['name'].lower() and not ch.get('is_archived', False)
        ]
        return client_channels
    except SlackApiError as e:
        print(f"Error listing channels: {e}", file=sys.stderr)
        return []


def get_channel_messages(slack_client, channel_id, since_hours=72):
    """Get messages from a channel"""
    try:
        oldest = (datetime.now() - timedelta(hours=since_hours)).timestamp()
        response = slack_client.conversations_history(
            channel=channel_id,
            oldest=str(oldest),
            limit=200
        )
        return response.get('messages', [])
    except SlackApiError:
        return []


def get_user_info(slack_client, user_id, user_cache):
    """Get user info with caching"""
    if user_id in user_cache:
        return user_cache[user_id]

    try:
        response = slack_client.users_info(user=user_id)
        user_data = {
            'name': response['user'].get('real_name', 'Unknown'),
            'is_bot': response['user'].get('is_bot', False)
        }
        user_cache[user_id] = user_data
        return user_data
    except:
        user_cache[user_id] = {'name': 'Unknown', 'is_bot': False}
        return user_cache[user_id]


def message_has_team_reaction(msg, team_slack_ids):
    """Check if a message has a reaction from a team member"""
    reactions = msg.get('reactions', [])
    for reaction in reactions:
        # Each reaction has a list of user IDs who reacted
        reacting_users = reaction.get('users', [])
        for user_id in reacting_users:
            if user_id in team_slack_ids:
                return True
    return False


def analyze_sentiment(text):
    """Analyze sentiment of a message"""
    text_lower = text.lower()

    positive_score = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    negative_score = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)

    has_question = any(re.search(pattern, text_lower) for pattern in QUESTION_PATTERNS)

    if negative_score > positive_score:
        return 'negative', negative_score
    elif positive_score > negative_score:
        return 'positive', positive_score
    elif has_question:
        return 'questioning', 1
    else:
        return 'neutral', 0


def calculate_response_times(messages, slack_client, user_cache, team_slack_ids):
    """Calculate average response time to client messages"""
    if not messages:
        return None, []

    # Sort messages by timestamp (oldest first)
    sorted_msgs = sorted(messages, key=lambda m: float(m.get('ts', 0)))

    response_times = []
    unanswered = []

    pending_client_msg = None  # Client message waiting for team response
    pending_client_time = None
    pending_client_user = None

    for msg in sorted_msgs:
        user_id = msg.get('user', '')
        user_info = get_user_info(slack_client, user_id, user_cache)
        text = msg.get('text', '')

        # Skip bot messages
        if user_info.get('is_bot'):
            continue

        ts = float(msg.get('ts', 0))
        msg_time = datetime.fromtimestamp(ts)

        is_team_member = user_id in team_slack_ids

        if is_team_member:
            # Team member responded - if there was a pending client message, calculate response time
            if pending_client_msg and pending_client_time:
                response_time = (msg_time - pending_client_time).total_seconds() / 3600
                if response_time < 48:
                    response_times.append(response_time)
                pending_client_msg = None
                pending_client_time = None
                pending_client_user = None
        else:
            # This is a client message
            # Only track if it actually needs a response AND hasn't been acknowledged with a reaction
            if needs_response(text):
                # Check if a team member already reacted to this message (emoji acknowledgment)
                if message_has_team_reaction(msg, team_slack_ids):
                    # Message was acknowledged with a reaction, no text response needed
                    continue

                pending_client_msg = msg
                pending_client_time = msg_time
                pending_client_user = user_info['name']

    # Check if there's an unanswered client message
    if pending_client_msg and pending_client_time:
        hours_ago = (datetime.now() - pending_client_time).total_seconds() / 3600
        text = pending_client_msg.get('text', '')

        # Only flag if it's been more than 4 hours AND the message needs a response
        if hours_ago > 4:
            unanswered.append({
                'text': text[:100],
                'user': pending_client_user,
                'hours_ago': round(hours_ago, 1),
                'timestamp': pending_client_time.strftime('%Y-%m-%d %H:%M')
            })

    avg_response = sum(response_times) / len(response_times) if response_times else None
    return avg_response, unanswered


def get_video_stats_by_client(videos, clients):
    """Get video statistics grouped by client"""
    # Build client lookup
    client_lookup = {}
    for c in clients:
        client_lookup[c['id']] = {
            'name': c['fields'].get('Name', 'Unknown'),
            'status': c['fields'].get('Status', ''),
            'deliverables': c['fields'].get('Deliverables', ''),
        }

    # Group videos by client
    client_videos = defaultdict(list)

    for video in videos:
        fields = video['fields']
        client_ids = fields.get('Client', [])
        if not client_ids:
            continue

        client_id = client_ids[0]
        client_info = client_lookup.get(client_id, {'name': 'Unknown', 'status': ''})

        # Skip non-current clients
        if client_info['status'] not in ['Current', 'Onboarding']:
            continue

        client_name = client_info['name']

        record_id = video['id']
        video_data = {
            'video_id': fields.get('Video ID', 'Unknown'),
            'record_id': record_id,
            'airtable_url': get_airtable_record_url('Videos', record_id),
            'status': fields.get('Editing Status', ''),
            'deadline': fields.get('Deadline', ''),
            'editor': (fields.get("Editor's Name", ['Unassigned']) or ['Unassigned'])[0],
        }

        client_videos[client_name].append(video_data)

    # Calculate stats per client
    stats = {}
    today = datetime.now().date()

    for client_name, vids in client_videos.items():
        total = len(vids)
        completed = sum(1 for v in vids if '100 -' in v['status'] or 'DONE' in v['status'])
        in_progress = sum(1 for v in vids if v['status'] and '100 -' not in v['status'] and 'DONE' not in v['status'])

        overdue_count = 0
        due_soon_count = 0
        overdue_videos = []
        due_soon_videos = []

        for v in vids:
            if '100 -' in v['status'] or 'DONE' in v['status'] or '75 -' in v['status']:
                continue

            deadline_str = v.get('deadline', '')
            if deadline_str:
                try:
                    deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
                    days_until = (deadline - today).days
                    if days_until < 0:
                        overdue_count += 1
                        overdue_videos.append({
                            'video_id': v['video_id'],
                            'days_overdue': abs(days_until),
                            'deadline': deadline_str,
                            'status': v['status'],
                            'editor': v['editor'],
                            'airtable_url': v.get('airtable_url'),
                        })
                    elif days_until <= 3:
                        due_soon_count += 1
                        due_soon_videos.append({
                            'video_id': v['video_id'],
                            'days_until': days_until,
                            'deadline': deadline_str,
                            'status': v['status'],
                            'editor': v['editor'],
                            'airtable_url': v.get('airtable_url'),
                        })
                except:
                    pass

        # Get active (non-completed) videos
        active_videos = [v for v in vids if '100 -' not in v['status'] and 'DONE' not in v['status']]

        stats[client_name] = {
            'total_videos': total,
            'completed': completed,
            'in_progress': in_progress,
            'overdue': overdue_count,
            'overdue_videos': sorted(overdue_videos, key=lambda x: x['days_overdue'], reverse=True),
            'due_soon': due_soon_count,
            'due_soon_videos': sorted(due_soon_videos, key=lambda x: x['days_until']),
            'active_videos': active_videos[:5],
            'completion_rate': round(completed / total * 100, 1) if total > 0 else 0
        }

    return stats, client_lookup


def generate_client_report(hours=72, target_client=None):
    """Generate comprehensive client status and sentiment report"""

    print("Fetching Airtable data...", file=sys.stderr)
    videos, clients = get_airtable_data()

    print("Fetching team Slack IDs...", file=sys.stderr)
    team_slack_ids = get_team_slack_ids()
    print(f"  Found {len(team_slack_ids)} team members", file=sys.stderr)

    print("Connecting to Slack...", file=sys.stderr)
    slack_client = get_slack_client()

    print("Getting client channels...", file=sys.stderr)
    client_channels = get_client_channels(slack_client)

    print("Analyzing video stats...", file=sys.stderr)
    video_stats, client_lookup = get_video_stats_by_client(videos, clients)

    user_cache = {}
    reports = []

    print(f"Analyzing {len(client_channels)} client channels...", file=sys.stderr)

    for channel in client_channels:
        channel_name = channel['name']
        channel_id = channel['id']

        # Extract client name from channel (e.g., "josh-client" -> "Josh")
        client_name_from_channel = channel_name.replace('-client', '').replace('-', ' ').title()

        # Try to match with Airtable client
        matched_client = None
        for airtable_name in video_stats.keys():
            if airtable_name.lower() in client_name_from_channel.lower() or \
               client_name_from_channel.lower() in airtable_name.lower():
                matched_client = airtable_name
                break

        # Filter by target client if specified
        if target_client:
            if not matched_client or target_client.lower() not in matched_client.lower():
                continue

        # Get messages
        messages = get_channel_messages(slack_client, channel_id, hours)

        if not messages:
            continue

        # Analyze sentiment
        sentiment_scores = {'positive': 0, 'negative': 0, 'neutral': 0, 'questioning': 0}
        notable_messages = []

        for msg in messages:
            text = msg.get('text', '')
            if not text or len(text) < 5:
                continue

            sentiment, score = analyze_sentiment(text)
            sentiment_scores[sentiment] += 1

            if sentiment in ['negative', 'questioning'] and score > 0:
                user_id = msg.get('user', '')
                user_info = get_user_info(slack_client, user_id, user_cache)
                ts = float(msg.get('ts', 0))
                msg_time = datetime.fromtimestamp(ts)

                notable_messages.append({
                    'text': text[:150],
                    'user': user_info['name'],
                    'time': msg_time.strftime('%Y-%m-%d %H:%M'),
                    'sentiment': sentiment
                })

        # Calculate response times (now properly distinguishes team vs client messages)
        avg_response, unanswered = calculate_response_times(messages, slack_client, user_cache, team_slack_ids)

        # Get video stats for this client
        client_video_stats = video_stats.get(matched_client, {})

        # Determine overall mood
        total_sentiment = sum(sentiment_scores.values())
        if total_sentiment > 0:
            neg_ratio = sentiment_scores['negative'] / total_sentiment
            pos_ratio = sentiment_scores['positive'] / total_sentiment
            question_ratio = sentiment_scores['questioning'] / total_sentiment

            if neg_ratio > 0.3:
                overall_mood = 'Concerned'
            elif pos_ratio > 0.4:
                overall_mood = 'Happy'
            elif question_ratio > 0.3:
                overall_mood = 'Seeking Updates'
            else:
                overall_mood = 'Neutral'
        else:
            overall_mood = 'Quiet'

        # Risk assessment
        risk_factors = []
        if client_video_stats.get('overdue', 0) > 0:
            risk_factors.append(f"{client_video_stats['overdue']} overdue video(s)")
        if sentiment_scores['negative'] > 2:
            risk_factors.append("Multiple negative messages")
        if unanswered:
            risk_factors.append(f"{len(unanswered)} unanswered message(s)")
        if avg_response and avg_response > 12:
            risk_factors.append(f"Slow avg response ({round(avg_response, 1)}h)")

        risk_level = 'High' if len(risk_factors) >= 2 else ('Medium' if risk_factors else 'Low')

        report = {
            'client_name': matched_client or client_name_from_channel,
            'channel': channel_name,
            'channel_id': channel_id,
            'message_count': len(messages),
            'overall_mood': overall_mood,
            'sentiment_breakdown': sentiment_scores,
            'risk_level': risk_level,
            'risk_factors': risk_factors,
            'avg_response_time_hours': round(avg_response, 1) if avg_response else None,
            'unanswered_messages': unanswered[:3],  # Top 3
            'notable_messages': notable_messages[:5],  # Top 5
            'video_stats': client_video_stats,
        }

        reports.append(report)

    # Sort by risk level
    risk_order = {'High': 0, 'Medium': 1, 'Low': 2}
    reports.sort(key=lambda r: (risk_order.get(r['risk_level'], 3), -r['message_count']))

    return reports


def main():
    parser = argparse.ArgumentParser(description='Generate client status and sentiment report')
    parser.add_argument('--hours', type=int, default=72,
                        help='Hours to look back (default: 72)')
    parser.add_argument('--client', type=str, default=None,
                        help='Filter to specific client')
    parser.add_argument('--output', choices=['json', 'summary'], default='summary',
                        help='Output format')

    args = parser.parse_args()

    try:
        reports = generate_client_report(hours=args.hours, target_client=args.client)

        if args.output == 'json':
            print(json.dumps(reports, indent=2))
        else:
            print("\n" + "="*70)
            print("CLIENT STATUS & SENTIMENT REPORT")
            print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            print(f"Looking back: {args.hours} hours")
            print("="*70)

            if not reports:
                print("\nNo client channel activity found.")
                return 0

            # Summary section
            high_risk = [r for r in reports if r['risk_level'] == 'High']
            medium_risk = [r for r in reports if r['risk_level'] == 'Medium']

            print(f"\n## SUMMARY")
            print(f"Total clients analyzed: {len(reports)}")
            print(f"High risk: {len(high_risk)} | Medium risk: {len(medium_risk)} | Low risk: {len(reports) - len(high_risk) - len(medium_risk)}")

            # High risk clients first
            if high_risk:
                print(f"\n{'='*70}")
                print("## HIGH RISK CLIENTS - NEED ATTENTION")
                print("="*70)

                for r in high_risk:
                    print(f"\n### {r['client_name']} (#{r['channel']})")
                    print(f"    Mood: {r['overall_mood']} | Messages: {r['message_count']}")
                    print(f"    Risk factors:")
                    for rf in r['risk_factors']:
                        print(f"      - {rf}")

                    vs = r.get('video_stats', {})
                    if vs:
                        print(f"    Videos: {vs.get('in_progress', 0)} active, {vs.get('overdue', 0)} overdue, {vs.get('due_soon', 0)} due soon")

                        # Show overdue videos with Airtable links
                        if vs.get('overdue_videos'):
                            print(f"    Overdue videos:")
                            for ov in vs['overdue_videos'][:3]:
                                url = ov.get('airtable_url', '')
                                print(f"      - Video #{ov['video_id']} ({ov['days_overdue']}d overdue) - {ov['editor']}")
                                if url:
                                    print(f"        {url}")

                        # Show due soon videos with Airtable links
                        if vs.get('due_soon_videos'):
                            print(f"    Due soon:")
                            for dv in vs['due_soon_videos'][:3]:
                                url = dv.get('airtable_url', '')
                                print(f"      - Video #{dv['video_id']} (in {dv['days_until']}d) - {dv['editor']}")
                                if url:
                                    print(f"        {url}")

                    if r['unanswered_messages']:
                        print(f"    Unanswered:")
                        for um in r['unanswered_messages'][:2]:
                            print(f"      [{um['hours_ago']}h ago] \"{um['text'][:60]}...\"")

                    if r['notable_messages']:
                        print(f"    Notable messages:")
                        for nm in r['notable_messages'][:2]:
                            print(f"      [{nm['sentiment']}] {nm['user']}: \"{nm['text'][:60]}...\"")

            # Medium risk
            if medium_risk:
                print(f"\n{'='*70}")
                print("## MEDIUM RISK CLIENTS")
                print("="*70)

                for r in medium_risk:
                    print(f"\n### {r['client_name']}")
                    print(f"    Mood: {r['overall_mood']} | Risk: {', '.join(r['risk_factors'])}")
                    vs = r.get('video_stats', {})
                    if vs:
                        print(f"    Videos: {vs.get('in_progress', 0)} active, {vs.get('overdue', 0)} overdue")

            # All clients summary table
            print(f"\n{'='*70}")
            print("## ALL CLIENTS OVERVIEW")
            print("="*70)
            print(f"\n{'Client':<20} {'Mood':<15} {'Risk':<8} {'Active':<8} {'Overdue':<8} {'Messages':<8}")
            print("-"*70)

            for r in reports:
                vs = r.get('video_stats', {})
                print(f"{r['client_name'][:19]:<20} {r['overall_mood']:<15} {r['risk_level']:<8} {vs.get('in_progress', '-'):<8} {vs.get('overdue', '-'):<8} {r['message_count']:<8}")

        return 0

    except Exception as e:
        print(json.dumps({'error': str(e)}))
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
