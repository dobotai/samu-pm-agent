#!/usr/bin/env python3
"""
PM Daily Report - Comprehensive daily status report for Project Managers
Part of DOEBI execution layer

This script generates a complete daily report aligned with PM SOP daily tasks:
1. Videos requiring QC (priority task)
2. Videos ready to schedule on YouTube
3. Videos in revision needing follow-up
4. Videos sent to client awaiting review
5. Overdue and upcoming deadline tracking
6. Blocker analysis (us vs client) via Slack context
7. Editor check-in monitoring
8. Payment day reminders (15th/30th)

Usage:
    python pm_daily_report.py                    # Today's report
    python pm_daily_report.py --date 2026-01-22  # Specific date
    python pm_daily_report.py --output json      # JSON output
    python pm_daily_report.py --no-slack         # Skip Slack analysis (faster)
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pyairtable import Api
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


def get_airtable_connection():
    """Initialize Airtable API connection"""
    api_key = os.getenv('AIRTABLE_API_KEY')
    base_id = os.getenv('AIRTABLE_BASE_ID')
    if not api_key or not base_id:
        raise ValueError("AIRTABLE_API_KEY and AIRTABLE_BASE_ID required")
    return Api(api_key), base_id


def get_slack_client():
    """Initialize Slack client"""
    token = os.getenv('SLACK_USER_TOKEN') or os.getenv('SLACK_BOT_TOKEN')
    if not token:
        return None
    return WebClient(token=token)


def get_anthropic_client():
    """Initialize Anthropic client"""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return None
    return Anthropic(api_key=api_key)


def fetch_lookup_tables(api, base_id):
    """Fetch Team and Clients tables for name lookups"""
    team_table = api.table(base_id, "Team")
    clients_table = api.table(base_id, "Clients")

    team_records = team_table.all(fields=["Name"])
    client_records = clients_table.all(fields=["Name"])

    editors = {r['id']: r['fields'].get('Name', 'Unknown') for r in team_records}
    clients = {r['id']: r['fields'].get('Name', 'Unknown') for r in client_records}

    return editors, clients


def fetch_slack_channels(slack_client):
    """Fetch all Slack channels and build a lookup by name"""
    if not slack_client:
        return {}

    try:
        response = slack_client.conversations_list(
            types='public_channel,private_channel',
            limit=1000
        )
        channels = {}
        for ch in response['channels']:
            channels[ch['name'].lower()] = ch['id']
        return channels
    except SlackApiError:
        return {}


def get_client_channel_id(client_name, channels):
    """Get the Slack channel ID for a client"""
    # Try common naming patterns
    patterns = [
        f"{client_name.lower()}-client",
        f"{client_name.lower().replace(' ', '-')}-client",
        client_name.lower(),
        client_name.lower().replace(' ', '-'),
    ]

    for pattern in patterns:
        if pattern in channels:
            return channels[pattern]

    return None


def get_editor_channel_id(editor_name, channels):
    """Get the Slack channel ID for an editor"""
    if not editor_name or editor_name == 'Unassigned':
        return None

    # Try common naming patterns
    patterns = [
        f"{editor_name.lower()}-editing",
        f"{editor_name.lower().replace(' ', '-')}-editing",
        f"{editor_name.lower()}-editor",
    ]

    for pattern in patterns:
        if pattern in channels:
            return channels[pattern]

    return None


def fetch_slack_messages(slack_client, channel_id, hours=72, limit=50):
    """Fetch recent messages from a Slack channel"""
    if not slack_client or not channel_id:
        return []

    try:
        oldest = (datetime.now() - timedelta(hours=hours)).timestamp()
        response = slack_client.conversations_history(
            channel=channel_id,
            limit=limit,
            oldest=str(oldest)
        )

        messages = []
        for msg in response.get('messages', []):
            ts = float(msg.get('ts', 0))
            dt = datetime.fromtimestamp(ts)
            messages.append({
                'text': msg.get('text', ''),
                'datetime': dt.strftime('%Y-%m-%d %H:%M'),
                'user': msg.get('user', 'unknown')
            })

        return messages
    except SlackApiError:
        return []


def analyze_video_context(anthropic_client, video, client_messages, editor_messages):
    """Use Claude to analyze whether a video delay is our fault or client-side"""
    if not anthropic_client:
        return None

    # Need at least some messages to analyze
    if not client_messages and not editor_messages:
        return None

    # Build context for Claude
    client_messages_text = "\n".join([
        f"[{m['datetime']}]: {m['text']}"
        for m in client_messages[:25]
    ]) if client_messages else "(No messages found)"

    editor_messages_text = "\n".join([
        f"[{m['datetime']}]: {m['text']}"
        for m in editor_messages[:25]
    ]) if editor_messages else "(No messages found)"

    prompt = f"""Analyze this video production status and recent Slack messages to determine:
1. Is this delay caused by US (the production team) or the CLIENT?
2. What is the actual current situation?
3. What action is needed, if any?

VIDEO DETAILS:
- Video ID: {video['video_id']}
- Client: {video['client']}
- Editor: {video['editor']}
- Status: {video['status']}
- Deadline: {video['deadline']}
- Thumbnail Status: {video['thumbnail']}

RECENT SLACK MESSAGES FROM CLIENT CHANNEL #{video['client'].lower()}-client (most recent first):
{client_messages_text}

RECENT SLACK MESSAGES FROM EDITOR CHANNEL #{video['editor'].lower()}-editing (most recent first):
{editor_messages_text}

Use BOTH channels to understand the full picture. The editor channel may have internal context about blockers, while the client channel shows client communication.

Respond in this exact JSON format:
{{
    "blocker": "us" | "client" | "none" | "unclear",
    "summary": "One sentence explaining the actual situation based on both channels",
    "action_needed": "What needs to happen next, or 'none' if waiting on client",
    "priority": "high" | "medium" | "low"
}}

Only respond with the JSON, no other text."""

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse the response
        response_text = response.content[0].text.strip()
        # Handle potential markdown code blocks
        if response_text.startswith('```'):
            response_text = response_text.split('\n', 1)[1]
            response_text = response_text.rsplit('```', 1)[0]

        return json.loads(response_text)
    except Exception as e:
        return {"blocker": "unclear", "summary": f"Analysis failed: {str(e)}", "action_needed": "Manual review needed", "priority": "medium"}


def fetch_videos_by_filter(api, base_id, filter_formula):
    """Fetch videos matching a filter formula"""
    table = api.table(base_id, "Videos")
    fields = [
        "Video ID", "Client", "Editing Status", "Assigned Editor",
        "Deadline", "Thumbnail Status", "Video Number"
    ]
    return table.all(formula=filter_formula, fields=fields)


def format_video(record, editors, clients):
    """Format a video record with resolved names"""
    fields = record['fields']

    client_ids = fields.get('Client', [])
    client_name = clients.get(client_ids[0], 'Unknown') if client_ids else 'Unknown'

    editor_ids = fields.get('Assigned Editor', [])
    editor_name = editors.get(editor_ids[0], 'Unassigned') if editor_ids else 'Unassigned'

    video_num = fields.get('Video Number', '?')
    fmt = str(fields.get('Format', '')).lower()
    video_type = 'Shorts' if 'short' in fmt else 'Video'
    display_name = f"{client_name} {video_type} #{video_num}"

    return {
        'video_id': display_name,
        'client': client_name,
        'editor': editor_name,
        'status': fields.get('Editing Status', 'Unknown'),
        'deadline': fields.get('Deadline', 'No deadline'),
        'thumbnail': fields.get('Thumbnail Status', 'N/A'),
        'video_number': fields.get('Video Number', ''),
        'record_id': record['id']
    }


def generate_report(target_date=None, include_slack=True):
    """Generate the daily PM report with Slack context"""
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    target_dt = datetime.strptime(target_date, '%Y-%m-%d')
    tomorrow = (target_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    week_end = (target_dt + timedelta(days=6)).strftime('%Y-%m-%d')

    # Initialize connections
    api, base_id = get_airtable_connection()
    slack_client = get_slack_client() if include_slack else None
    anthropic_client = get_anthropic_client() if include_slack else None

    # Fetch lookups
    editors, clients = fetch_lookup_tables(api, base_id)
    channels = fetch_slack_channels(slack_client) if slack_client else {}

    # Define queries aligned with PM SOP daily tasks
    queries = {
        # PRIORITY: Videos needing QC (PM's #1 daily task)
        'needs_qc': "AND({Editing Status} = '60 - QC', {Deadline} != '')",

        # Videos ready to schedule on YouTube
        'ready_to_schedule': "AND({Editing Status} = '80 - Approved By Client', {Deadline} != '')",

        # Videos in revision - need to follow up with editors
        'in_revision': "AND({Editing Status} = '59 - Editor Revisions', {Deadline} != '')",

        # Videos sent to client awaiting their review
        'sent_to_client': "AND({Editing Status} = '75 - Sent for Review', {Deadline} != '')",

        # Deadline tracking
        'due_today': f"AND(IS_SAME({{Deadline}}, '{target_date}', 'day'), {{Editing Status}} != '100 - Scheduled - DONE')",
        'overdue_with_deadline': f"AND({{Deadline}} < '{target_date}', {{Deadline}} != '', {{Editing Status}} != '100 - Scheduled - DONE')",
        'due_tomorrow': f"AND(IS_SAME({{Deadline}}, '{tomorrow}', 'day'), {{Editing Status}} != '100 - Scheduled - DONE')",
        'due_this_week': f"AND({{Deadline}} > '{tomorrow}', {{Deadline}} <= '{week_end}', {{Editing Status}} != '100 - Scheduled - DONE')",

        # All active videos for status breakdown
        'all_active': "AND({Editing Status} != '100 - Scheduled - DONE', {Editing Status} != '', {Deadline} != '')",
    }

    results = {}
    for key, formula in queries.items():
        try:
            records = fetch_videos_by_filter(api, base_id, formula)
            results[key] = [format_video(r, editors, clients) for r in records]
        except Exception as e:
            results[key] = []
            print(f"Warning: Failed to fetch {key}: {e}", file=sys.stderr)

    # Sort overdue by deadline
    results['overdue_with_deadline'] = sorted(
        results['overdue_with_deadline'],
        key=lambda x: x['deadline']
    )

    # Analyze ALL videos that need attention (no arbitrary limit)
    # Include: overdue, due today, in revision, sent to client
    videos_to_analyze = (
        results['due_today'] +
        results['overdue_with_deadline'] +
        results.get('in_revision', []) +
        results.get('sent_to_client', [])
    )
    # Remove duplicates (a video might be in multiple categories)
    seen_ids = set()
    unique_videos = []
    for v in videos_to_analyze:
        if v['video_id'] not in seen_ids:
            seen_ids.add(v['video_id'])
            unique_videos.append(v)
    videos_to_analyze = unique_videos

    analyzed_videos = []
    if include_slack and slack_client and anthropic_client:
        for video in videos_to_analyze:
            client_channel_id = get_client_channel_id(video['client'], channels)
            editor_channel_id = get_editor_channel_id(video['editor'], channels)

            # Fetch messages from both channels
            client_messages = fetch_slack_messages(slack_client, client_channel_id, hours=72) if client_channel_id else []
            editor_messages = fetch_slack_messages(slack_client, editor_channel_id, hours=72) if editor_channel_id else []

            if client_messages or editor_messages:
                analysis = analyze_video_context(anthropic_client, video, client_messages, editor_messages)
            else:
                missing_channels = []
                if not client_channel_id:
                    missing_channels.append(f"{video['client']}-client")
                if not editor_channel_id:
                    missing_channels.append(f"{video['editor']}-editing")
                analysis = {
                    "blocker": "unclear",
                    "summary": f"No Slack channels found: {', '.join(missing_channels)}",
                    "action_needed": "Manual review needed",
                    "priority": "medium"
                }

            analyzed_videos.append({
                **video,
                'analysis': analysis,
                'has_client_channel': client_channel_id is not None,
                'has_editor_channel': editor_channel_id is not None
            })
    else:
        analyzed_videos = [{**v, 'analysis': None, 'has_client_channel': False, 'has_editor_channel': False} for v in videos_to_analyze]

    # Separate by blocker type
    def get_blocker(v):
        analysis = v.get('analysis')
        if analysis is None:
            return None
        return analysis.get('blocker')

    our_fault = [v for v in analyzed_videos if get_blocker(v) == 'us']
    client_fault = [v for v in analyzed_videos if get_blocker(v) == 'client']
    unclear = [v for v in analyzed_videos if get_blocker(v) in ['unclear', 'none', None]]

    # Check if today is a payment day (15th or 30th)
    day_of_month = target_dt.day
    is_payment_day = day_of_month in [15, 30]

    # Build status breakdown from all active videos
    status_breakdown = {}
    for video in results.get('all_active', []):
        status = video['status']
        status_breakdown[status] = status_breakdown.get(status, 0) + 1

    # Group videos by editor for check-in tracking
    editors_with_active = {}
    for video in results.get('all_active', []):
        editor = video['editor']
        if editor and editor != 'Unassigned':
            if editor not in editors_with_active:
                editors_with_active[editor] = []
            editors_with_active[editor].append(video)

    return {
        'date': target_date,
        'generated_at': datetime.now().isoformat(),
        'is_payment_day': is_payment_day,

        # Priority action items (aligned with PM SOP)
        'needs_qc': results.get('needs_qc', []),
        'ready_to_schedule': results.get('ready_to_schedule', []),
        'in_revision': results.get('in_revision', []),
        'sent_to_client': results.get('sent_to_client', []),

        # Deadline tracking
        'due_today': results['due_today'],
        'overdue_with_deadline': results['overdue_with_deadline'],
        'due_tomorrow': results['due_tomorrow'],
        'due_this_week': sorted(results['due_this_week'], key=lambda x: x['deadline']),

        # Blocker analysis
        'analysis': {
            'our_fault': our_fault,
            'client_fault': client_fault,
            'unclear': unclear
        },

        # Summary data
        'status_breakdown': dict(sorted(status_breakdown.items())),
        'editors_with_active': editors_with_active,

        'counts': {
            'needs_qc': len(results.get('needs_qc', [])),
            'ready_to_schedule': len(results.get('ready_to_schedule', [])),
            'in_revision': len(results.get('in_revision', [])),
            'sent_to_client': len(results.get('sent_to_client', [])),
            'due_today': len(results['due_today']),
            'overdue': len(results['overdue_with_deadline']),
            'due_tomorrow': len(results['due_tomorrow']),
            'due_this_week': len(results['due_this_week']),
            'our_blockers': len(our_fault),
            'client_blockers': len(client_fault),
            'total_active': len(results.get('all_active', [])),
        }
    }


def print_report(report):
    """Print a formatted text report aligned with PM SOP daily tasks"""
    print(f"\n{'='*70}")
    print(f"PM DAILY REPORT - {report['date']}")
    print(f"{'='*70}\n")

    # Payment day alert
    if report.get('is_payment_day'):
        print("*** PAYMENT DAY ***")
        print("Remember to message all editors:")
        print("'Hey, we're paying you today. Please send over how much $ we owe you")
        print("and a breakdown of the videos you did. Thank you!'")
        print()

    counts = report['counts']
    print("OVERVIEW")
    print(f"  [PRIORITY] Videos to QC:     {counts['needs_qc']}")
    print(f"  [PRIORITY] Ready to Schedule: {counts['ready_to_schedule']}")
    print(f"  Videos in Revision:           {counts['in_revision']}")
    print(f"  Sent to Client (awaiting):    {counts['sent_to_client']}")
    print(f"  Due Today:                    {counts['due_today']}")
    print(f"  Overdue:                      {counts['overdue']}")
    print(f"  Due Tomorrow:                 {counts['due_tomorrow']}")
    print(f"  Due This Week:                {counts['due_this_week']}")
    print(f"  Our Blockers:                 {counts['our_blockers']}")
    print(f"  Client Blockers:              {counts['client_blockers']}")
    print(f"  Total Active:                 {counts['total_active']}")

    # PRIORITY 1: Videos needing QC
    needs_qc = report.get('needs_qc', [])
    if needs_qc:
        print(f"\n{'-'*70}")
        print(f"[PRIORITY 1] VIDEOS NEEDING QC ({len(needs_qc)} videos)")
        print(f"{'-'*70}")
        print("Do these FIRST - your #1 daily task!")
        for v in needs_qc:
            print(f"  {v['video_id']:<30} | {v['editor']:<12} | Due: {v['deadline']}")

    # PRIORITY 2: Ready to Schedule
    ready = report.get('ready_to_schedule', [])
    if ready:
        print(f"\n{'-'*70}")
        print(f"[PRIORITY 2] READY TO SCHEDULE ON YOUTUBE ({len(ready)} videos)")
        print(f"{'-'*70}")
        print("Client approved - schedule these on YouTube!")
        for v in ready:
            print(f"  {v['video_id']:<30} | Due: {v['deadline']}")

    # Videos in Revision - need follow-up with editors
    in_revision = report.get('in_revision', [])
    if in_revision:
        print(f"\n{'-'*70}")
        print(f"VIDEOS IN REVISION ({len(in_revision)} videos)")
        print(f"{'-'*70}")
        print("Check with editors on progress!")
        for v in in_revision:
            print(f"  {v['video_id']:<30} | {v['editor']:<12} | Due: {v['deadline']}")

    # Sent to Client - awaiting review
    sent_to_client = report.get('sent_to_client', [])
    if sent_to_client:
        print(f"\n{'-'*70}")
        print(f"SENT TO CLIENT - AWAITING REVIEW ({len(sent_to_client)} videos)")
        print(f"{'-'*70}")
        print("Waiting on client feedback - follow up if needed")
        for v in sent_to_client:
            print(f"  {v['video_id']:<30} | Due: {v['deadline']}")

    # ACTION REQUIRED - Our fault
    our_fault = report['analysis']['our_fault']
    if our_fault:
        print(f"\n{'-'*70}")
        print(f"ACTION REQUIRED - OUR BLOCKERS ({len(our_fault)} videos)")
        print(f"{'-'*70}")
        for v in our_fault:
            analysis = v.get('analysis', {})
            print(f"\n  {v['video_id']} | {v['editor']} | Due: {v['deadline']}")
            print(f"  Status: {v['status']}")
            print(f"  >> {analysis.get('summary', 'No analysis')}")
            print(f"  Action: {analysis.get('action_needed', 'Unknown')}")

    # WAITING ON CLIENT
    client_fault = report['analysis']['client_fault']
    if client_fault:
        print(f"\n{'-'*70}")
        print(f"WAITING ON CLIENT ({len(client_fault)} videos)")
        print(f"{'-'*70}")
        for v in client_fault:
            analysis = v.get('analysis', {})
            print(f"\n  {v['video_id']} | Due: {v['deadline']}")
            print(f"  Status: {v['status']}")
            print(f"  >> {analysis.get('summary', 'No analysis')}")

    # NEEDS REVIEW
    unclear = report['analysis']['unclear']
    if unclear:
        print(f"\n{'-'*70}")
        print(f"NEEDS MANUAL REVIEW ({len(unclear)} videos)")
        print(f"{'-'*70}")
        for v in unclear[:10]:  # Limit display
            print(f"  Video {v['video_id']} | {v['client']} | {v['editor']} | Due: {v['deadline']} | {v['status']}")
        if len(unclear) > 10:
            print(f"  ... and {len(unclear) - 10} more")

    # DUE TODAY
    print(f"\n{'-'*70}")
    print(f"DUE TODAY ({len(report['due_today'])} videos)")
    print(f"{'-'*70}")
    if report['due_today']:
        for v in report['due_today']:
            print(f"  {v['video_id']:<6} | {v['client']:<18} | {v['editor']:<12} | {v['status']}")
    else:
        print("  No videos due today")

    # DUE TOMORROW
    print(f"\n{'-'*70}")
    print(f"DUE TOMORROW ({len(report['due_tomorrow'])} videos)")
    print(f"{'-'*70}")
    if report['due_tomorrow']:
        for v in report['due_tomorrow']:
            print(f"  {v['video_id']:<6} | {v['client']:<18} | {v['editor']:<12} | {v['status']}")
    else:
        print("  No videos due tomorrow")

    # DUE THIS WEEK
    print(f"\n{'-'*70}")
    print(f"DUE THIS WEEK ({len(report['due_this_week'])} videos)")
    print(f"{'-'*70}")
    if report['due_this_week']:
        for v in report['due_this_week'][:15]:
            print(f"  {v['deadline']} | {v['video_id']:<6} | {v['client']:<18} | {v['editor']:<12} | {v['status'][:25]}")
        if len(report['due_this_week']) > 15:
            print(f"  ... and {len(report['due_this_week']) - 15} more")
    else:
        print("  No videos due this week")

    # EDITORS WITH ACTIVE VIDEOS
    editors = report.get('editors_with_active', {})
    if editors:
        print(f"\n{'-'*70}")
        print(f"EDITOR WORKLOAD (check in with these editors)")
        print(f"{'-'*70}")
        for editor, videos in sorted(editors.items()):
            video_count = len(videos)
            statuses = set(v['status'] for v in videos)
            print(f"  {editor:<15} | {video_count} active videos | Statuses: {', '.join(s[:20] for s in statuses)}")

    # STATUS BREAKDOWN
    status_breakdown = report.get('status_breakdown', {})
    if status_breakdown:
        print(f"\n{'-'*70}")
        print(f"STATUS BREAKDOWN (all active videos)")
        print(f"{'-'*70}")
        for status, count in status_breakdown.items():
            print(f"  {count:>3} | {status}")

    print(f"\n{'='*70}")
    print(f"Generated at: {report['generated_at']}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Generate PM daily report with Slack context',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--date', help='Target date (YYYY-MM-DD, default: today)')
    parser.add_argument('--output', choices=['text', 'json'], default='text')
    parser.add_argument('--no-slack', action='store_true',
                       help='Skip Slack analysis (faster, but no context)')

    args = parser.parse_args()

    try:
        report = generate_report(
            target_date=args.date,
            include_slack=not args.no_slack
        )

        if args.output == 'json':
            print(json.dumps(report, indent=2))
        else:
            print_report(report)

        return 0

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
