#!/usr/bin/env python3
"""
Daily Summary Tool - Generates a complete daily status report from Airtable
Part of DOEBI execution layer (deterministic tool)

Usage:
    python daily_summary.py                    # Today's summary
    python daily_summary.py --date 2026-01-22  # Specific date
    python daily_summary.py --output json      # JSON output for programmatic use

Output includes:
    - Videos due today
    - Overdue videos (not done, deadline passed)
    - Due tomorrow
    - Due this week
    - Status breakdown by editing stage
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pyairtable import Api
from dotenv import load_dotenv

load_dotenv()


def get_airtable_connection():
    """Initialize Airtable API connection"""
    api_key = os.getenv('AIRTABLE_API_KEY')
    base_id = os.getenv('AIRTABLE_BASE_ID')

    if not api_key:
        raise ValueError("AIRTABLE_API_KEY not found in environment variables")
    if not base_id:
        raise ValueError("AIRTABLE_BASE_ID not found in environment variables")

    return Api(api_key), base_id


def fetch_lookup_tables(api, base_id):
    """Fetch Team and Clients tables for name lookups"""
    team_table = api.table(base_id, "Team")
    clients_table = api.table(base_id, "Clients")

    team_records = team_table.all(fields=["Name"])
    client_records = clients_table.all(fields=["Name"])

    editors = {r['id']: r['fields'].get('Name', 'Unknown') for r in team_records}
    clients = {r['id']: r['fields'].get('Name', 'Unknown') for r in client_records}

    return editors, clients


def fetch_videos_by_filter(api, base_id, filter_formula, fields=None):
    """Fetch videos matching a filter formula"""
    table = api.table(base_id, "Videos")
    default_fields = [
        "Video ID", "Client", "Editing Status", "Assigned Editor",
        "Deadline", "Thumbnail Status", "Video Number"
    ]
    return table.all(formula=filter_formula, fields=fields or default_fields)


def format_video(record, editors, clients):
    """Format a video record with resolved names"""
    fields = record['fields']

    # Resolve client name
    client_ids = fields.get('Client', [])
    client_name = clients.get(client_ids[0], 'Unknown') if client_ids else 'Unknown'

    # Resolve editor name
    editor_ids = fields.get('Assigned Editor', [])
    editor_name = editors.get(editor_ids[0], 'Unassigned') if editor_ids else 'Unassigned'

    return {
        'video_id': fields.get('Video ID'),
        'client': client_name,
        'editor': editor_name,
        'status': fields.get('Editing Status', 'Unknown'),
        'deadline': fields.get('Deadline', 'No deadline'),
        'thumbnail': fields.get('Thumbnail Status', 'N/A'),
        'video_number': fields.get('Video Number', ''),
        'record_id': record['id']
    }


def generate_summary(target_date=None):
    """Generate the daily summary report"""
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')

    # Parse the target date
    target_dt = datetime.strptime(target_date, '%Y-%m-%d')
    tomorrow = (target_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    week_end = (target_dt + timedelta(days=6)).strftime('%Y-%m-%d')

    api, base_id = get_airtable_connection()

    # Fetch lookup tables
    editors, clients = fetch_lookup_tables(api, base_id)

    # Define queries
    queries = {
        'due_today': f"IS_SAME({{Deadline}}, '{target_date}', 'day')",
        'overdue': f"AND({{Deadline}} < '{target_date}', {{Editing Status}} != '100 - Scheduled - DONE')",
        'due_tomorrow': f"IS_SAME({{Deadline}}, '{tomorrow}', 'day')",
        'due_this_week': f"AND({{Deadline}} > '{tomorrow}', {{Deadline}} <= '{week_end}', {{Editing Status}} != '100 - Scheduled - DONE')",
        'in_progress': f"AND({{Editing Status}} != '100 - Scheduled - DONE', {{Editing Status}} != '', {{Deadline}} != '')"
    }

    results = {}
    for key, formula in queries.items():
        try:
            records = fetch_videos_by_filter(api, base_id, formula)
            results[key] = [format_video(r, editors, clients) for r in records]
        except Exception as e:
            results[key] = []
            print(f"Warning: Failed to fetch {key}: {e}", file=sys.stderr)

    # Calculate status breakdown from in_progress
    status_counts = {}
    for video in results.get('in_progress', []):
        status = video['status']
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        'date': target_date,
        'generated_at': datetime.now().isoformat(),
        'due_today': results['due_today'],
        'overdue': sorted(results['overdue'], key=lambda x: x['deadline']),
        'due_tomorrow': results['due_tomorrow'],
        'due_this_week': sorted(results['due_this_week'], key=lambda x: x['deadline']),
        'status_breakdown': dict(sorted(status_counts.items())),
        'counts': {
            'due_today': len(results['due_today']),
            'overdue': len(results['overdue']),
            'due_tomorrow': len(results['due_tomorrow']),
            'due_this_week': len(results['due_this_week']),
            'total_in_progress': len(results['in_progress'])
        }
    }


def print_text_summary(summary):
    """Print a formatted text summary"""
    # Use ASCII characters for compatibility
    print(f"\n{'='*60}")
    print(f"DAILY SUMMARY - {summary['date']}")
    print(f"{'='*60}\n")

    # Counts overview
    counts = summary['counts']
    print(f"Overview:")
    print(f"  Due Today:       {counts['due_today']}")
    print(f"  Overdue:         {counts['overdue']}")
    print(f"  Due Tomorrow:    {counts['due_tomorrow']}")
    print(f"  Due This Week:   {counts['due_this_week']}")
    print(f"  Total Active:    {counts['total_in_progress']}")

    # Due Today
    print(f"\n{'-'*60}")
    print(f"DUE TODAY ({len(summary['due_today'])} videos)")
    print(f"{'-'*60}")
    if summary['due_today']:
        print(f"{'Video':<8} {'Client':<20} {'Editor':<12} {'Status':<30} {'Thumbnail'}")
        print(f"{'-'*8} {'-'*20} {'-'*12} {'-'*30} {'-'*20}")
        for v in summary['due_today']:
            print(f"{v['video_id']:<8} {v['client'][:20]:<20} {v['editor'][:12]:<12} {v['status'][:30]:<30} {v['thumbnail']}")
    else:
        print("  No videos due today")

    # Overdue
    print(f"\n{'-'*60}")
    print(f"OVERDUE ({len(summary['overdue'])} videos)")
    print(f"{'-'*60}")
    if summary['overdue']:
        print(f"{'Deadline':<12} {'Video':<8} {'Client':<18} {'Editor':<12} {'Status'}")
        print(f"{'-'*12} {'-'*8} {'-'*18} {'-'*12} {'-'*30}")
        for v in summary['overdue']:
            print(f"{v['deadline']:<12} {v['video_id']:<8} {v['client'][:18]:<18} {v['editor'][:12]:<12} {v['status']}")
    else:
        print("  No overdue videos")

    # Due Tomorrow
    print(f"\n{'-'*60}")
    print(f"DUE TOMORROW ({len(summary['due_tomorrow'])} videos)")
    print(f"{'-'*60}")
    if summary['due_tomorrow']:
        print(f"{'Video':<8} {'Client':<20} {'Editor':<12} {'Status':<30} {'Thumbnail'}")
        print(f"{'-'*8} {'-'*20} {'-'*12} {'-'*30} {'-'*20}")
        for v in summary['due_tomorrow']:
            print(f"{v['video_id']:<8} {v['client'][:20]:<20} {v['editor'][:12]:<12} {v['status'][:30]:<30} {v['thumbnail']}")
    else:
        print("  No videos due tomorrow")

    # Due This Week
    print(f"\n{'-'*60}")
    print(f"DUE THIS WEEK ({len(summary['due_this_week'])} videos)")
    print(f"{'-'*60}")
    if summary['due_this_week']:
        print(f"{'Deadline':<12} {'Video':<8} {'Client':<18} {'Editor':<12} {'Status'}")
        print(f"{'-'*12} {'-'*8} {'-'*18} {'-'*12} {'-'*30}")
        for v in summary['due_this_week']:
            print(f"{v['deadline']:<12} {v['video_id']:<8} {v['client'][:18]:<18} {v['editor'][:12]:<12} {v['status']}")
    else:
        print("  No videos due this week")

    # Status Breakdown
    print(f"\n{'-'*60}")
    print(f"STATUS BREAKDOWN (all active videos)")
    print(f"{'-'*60}")
    for status, count in summary['status_breakdown'].items():
        print(f"  {status}: {count}")

    print(f"\n{'='*60}")
    print(f"Generated at: {summary['generated_at']}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Generate daily summary report from Airtable',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                        # Today's summary
  %(prog)s --date 2026-01-22      # Summary for specific date
  %(prog)s --output json          # JSON output
  %(prog)s --output json > report.json  # Save to file
        """
    )

    parser.add_argument('--date', help='Target date (YYYY-MM-DD format, default: today)')
    parser.add_argument('--output', choices=['text', 'json'], default='text',
                       help='Output format (default: text)')

    args = parser.parse_args()

    try:
        summary = generate_summary(args.date)

        if args.output == 'json':
            print(json.dumps(summary, indent=2))
        else:
            print_text_summary(summary)

        return 0

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
