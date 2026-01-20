#!/usr/bin/env python3
"""
Slack-Airtable Cross-Check Tool
Compares Slack activity with Airtable status to identify discrepancies

Use cases:
1. Status verification - Editor says 'done' in Slack but Airtable not updated
2. Deadline follow-ups - Urgent items with no recent Slack activity
3. Communication gaps - Videos with no recent messages in editor channel

Usage:
    python slack_airtable_crosscheck.py [--check <type>] [--hours <num>]

Examples:
    python slack_airtable_crosscheck.py --check all
    python slack_airtable_crosscheck.py --check status
    python slack_airtable_crosscheck.py --check urgent --hours 48
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from pyairtable import Api
from dotenv import load_dotenv

load_dotenv()


def get_airtable_data():
    """Fetch videos and clients from Airtable"""
    api_key = os.getenv('AIRTABLE_API_KEY')
    base_id = os.getenv('AIRTABLE_BASE_ID', 'apph2RxHbsyqmCwxk')

    if not api_key:
        raise ValueError("AIRTABLE_API_KEY not found in environment variables")

    api = Api(api_key)

    # Get videos
    videos_table = api.table(base_id, 'Videos')
    videos = videos_table.all()

    # Get clients
    clients_table = api.table(base_id, 'Clients')
    clients = clients_table.all()

    # Build client lookup
    client_lookup = {}
    for c in clients:
        client_lookup[c['id']] = {
            'name': c['fields'].get('Name', 'Unknown'),
            'status': c['fields'].get('Status', ''),
            'deliverables': c['fields'].get('Deliverables', ''),
        }

    return videos, client_lookup


def get_slack_client():
    """Initialize Slack client"""
    token = os.getenv('SLACK_USER_TOKEN') or os.getenv('SLACK_BOT_TOKEN')
    if not token:
        raise ValueError("SLACK_USER_TOKEN or SLACK_BOT_TOKEN not found")
    return WebClient(token=token)


def get_channel_messages(client, channel_id, since_hours=48):
    """Get recent messages from a channel"""
    try:
        oldest = (datetime.now() - timedelta(hours=since_hours)).timestamp()
        response = client.conversations_history(
            channel=channel_id,
            oldest=str(oldest),
            limit=100
        )
        return response.get('messages', [])
    except SlackApiError as e:
        # Channel might not be accessible
        return []


def check_status_discrepancies(videos, client_lookup, slack_client, hours=48):
    """
    Find videos where Slack mentions completion but Airtable status is behind
    """
    discrepancies = []
    completion_keywords = ['done', 'finished', 'completed', 'uploaded', 'sent', 'delivered', 'ready']

    for video in videos:
        fields = video['fields']
        video_id = fields.get('Video ID', 'Unknown')
        status = fields.get('Editing Status', '')
        channel_ids = fields.get("Editor's Slack Channel", []) or fields.get("Slack ID Channel (from Assigned Editor)", [])
        editor_name = (fields.get("Editor's Name", ['Unknown']) or ['Unknown'])[0]

        # Skip completed videos
        if '100 -' in status or 'DONE' in status:
            continue

        # Skip if no channel
        if not channel_ids:
            continue

        channel_id = channel_ids[0]
        messages = get_channel_messages(slack_client, channel_id, hours)

        # Look for completion keywords in recent messages
        for msg in messages:
            text = msg.get('text', '').lower()
            video_mentioned = str(video_id) in text or f"#{video_id}" in text

            for keyword in completion_keywords:
                if keyword in text and video_mentioned:
                    discrepancies.append({
                        'video_id': video_id,
                        'editor': editor_name,
                        'airtable_status': status,
                        'slack_message': msg.get('text', '')[:150],
                        'message_time': datetime.fromtimestamp(float(msg.get('ts', 0))).strftime('%Y-%m-%d %H:%M'),
                        'issue': f"Slack mentions '{keyword}' but Airtable status is '{status}'"
                    })
                    break

    return discrepancies


def check_urgent_without_activity(videos, client_lookup, slack_client, hours=48):
    """
    Find urgent/overdue videos with no recent Slack activity
    """
    silent_urgent = []
    today = datetime.now().date()

    for video in videos:
        fields = video['fields']
        video_id = fields.get('Video ID', 'Unknown')
        status = fields.get('Editing Status', '')
        deadline_str = fields.get('Deadline', '')
        channel_ids = fields.get("Editor's Slack Channel", []) or fields.get("Slack ID Channel (from Assigned Editor)", [])
        editor_name = (fields.get("Editor's Name", ['Unknown']) or ['Unknown'])[0]

        # Get client info
        client_ids = fields.get('Client', [])
        client_id = client_ids[0] if client_ids else None
        client_info = client_lookup.get(client_id, {'name': 'Unknown', 'status': ''})

        # Skip completed or sent to client
        if '100 -' in status or '75 -' in status or 'DONE' in status:
            continue

        # Skip non-current clients
        if client_info['status'] not in ['Current', 'Onboarding']:
            continue

        # Check if urgent (deadline within 3 days or overdue)
        is_urgent = False
        urgency_reason = ''

        if deadline_str and deadline_str.strip():
            try:
                deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
                days_until = (deadline - today).days
                if days_until < 0:
                    is_urgent = True
                    urgency_reason = f"OVERDUE by {abs(days_until)} days"
                elif days_until <= 3:
                    is_urgent = True
                    urgency_reason = f"Due in {days_until} days"
            except:
                pass

        if not is_urgent:
            continue

        # Check for recent Slack activity
        if not channel_ids:
            silent_urgent.append({
                'video_id': video_id,
                'editor': editor_name,
                'client': client_info['name'],
                'status': status,
                'urgency': urgency_reason,
                'issue': 'No Slack channel linked',
                'last_activity': 'N/A'
            })
            continue

        channel_id = channel_ids[0]
        messages = get_channel_messages(slack_client, channel_id, hours)

        # Filter for messages mentioning this video
        video_messages = [m for m in messages if str(video_id) in m.get('text', '')]

        if not video_messages:
            # No recent activity about this video
            silent_urgent.append({
                'video_id': video_id,
                'editor': editor_name,
                'client': client_info['name'],
                'status': status,
                'urgency': urgency_reason,
                'issue': f'No Slack activity about this video in last {hours} hours',
                'last_activity': 'None found'
            })

    return silent_urgent


def check_communication_gaps(videos, client_lookup, slack_client, hours=72):
    """
    Find active videos with no recent Slack messages in editor channel
    """
    gaps = []

    # Group videos by editor channel
    channel_videos = {}
    for video in videos:
        fields = video['fields']
        status = fields.get('Editing Status', '')

        # Only check active videos (not completed, not sent to client)
        if '100 -' in status or '75 -' in status or 'DONE' in status:
            continue

        channel_ids = fields.get("Editor's Slack Channel", []) or fields.get("Slack ID Channel (from Assigned Editor)", [])
        if channel_ids:
            channel_id = channel_ids[0]
            if channel_id not in channel_videos:
                channel_videos[channel_id] = []
            channel_videos[channel_id].append(video)

    # Check each channel
    for channel_id, vids in channel_videos.items():
        messages = get_channel_messages(slack_client, channel_id, hours)

        if not messages:
            # No messages at all in this channel
            editor_name = (vids[0]['fields'].get("Editor's Name", ['Unknown']) or ['Unknown'])[0]
            video_ids = [v['fields'].get('Video ID', '?') for v in vids]

            gaps.append({
                'editor': editor_name,
                'channel_id': channel_id,
                'active_videos': video_ids,
                'hours_silent': hours,
                'issue': f'No messages in channel for {hours}+ hours with {len(vids)} active video(s)'
            })

    return gaps


def main():
    parser = argparse.ArgumentParser(description='Cross-check Slack and Airtable data')
    parser.add_argument('--check', choices=['all', 'status', 'urgent', 'gaps'],
                        default='all', help='Type of check to run')
    parser.add_argument('--hours', type=int, default=48,
                        help='Hours to look back for Slack activity (default: 48)')
    parser.add_argument('--output', choices=['json', 'summary'], default='summary',
                        help='Output format')

    args = parser.parse_args()

    try:
        print("Fetching Airtable data...", file=sys.stderr)
        videos, client_lookup = get_airtable_data()

        print("Connecting to Slack...", file=sys.stderr)
        slack_client = get_slack_client()

        results = {}

        if args.check in ['all', 'status']:
            print("Checking status discrepancies...", file=sys.stderr)
            results['status_discrepancies'] = check_status_discrepancies(
                videos, client_lookup, slack_client, args.hours
            )

        if args.check in ['all', 'urgent']:
            print("Checking urgent items without activity...", file=sys.stderr)
            results['urgent_without_activity'] = check_urgent_without_activity(
                videos, client_lookup, slack_client, args.hours
            )

        if args.check in ['all', 'gaps']:
            print("Checking communication gaps...", file=sys.stderr)
            results['communication_gaps'] = check_communication_gaps(
                videos, client_lookup, slack_client, args.hours
            )

        if args.output == 'json':
            print(json.dumps(results, indent=2))
        else:
            # Summary output
            print("\n" + "="*60)
            print("SLACK-AIRTABLE CROSS-CHECK REPORT")
            print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            print(f"Looking back: {args.hours} hours")
            print("="*60 + "\n")

            if 'status_discrepancies' in results:
                items = results['status_discrepancies']
                print(f"## STATUS DISCREPANCIES ({len(items)} found)")
                if items:
                    for item in items:
                        print(f"\nVideo #{item['video_id']} ({item['editor']})")
                        print(f"  Airtable: {item['airtable_status']}")
                        print(f"  Slack ({item['message_time']}): \"{item['slack_message']}...\"")
                        print(f"  [!] {item['issue']}")
                else:
                    print("  None found - statuses appear in sync")
                print()

            if 'urgent_without_activity' in results:
                items = results['urgent_without_activity']
                print(f"## URGENT ITEMS WITHOUT SLACK ACTIVITY ({len(items)} found)")
                if items:
                    for item in items:
                        print(f"\nVideo #{item['video_id']} | {item['client']} | {item['editor']}")
                        print(f"  Status: {item['status']}")
                        print(f"  Urgency: {item['urgency']}")
                        print(f"  [!] {item['issue']}")
                else:
                    print("  None found - all urgent items have recent activity")
                print()

            if 'communication_gaps' in results:
                items = results['communication_gaps']
                print(f"## COMMUNICATION GAPS ({len(items)} found)")
                if items:
                    for item in items:
                        print(f"\nEditor: {item['editor']} (Channel: {item['channel_id']})")
                        print(f"  Active videos: {item['active_videos']}")
                        print(f"  [!] {item['issue']}")
                else:
                    print("  None found - all editor channels have recent activity")
                print()

        return 0

    except Exception as e:
        print(json.dumps({'error': str(e)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
