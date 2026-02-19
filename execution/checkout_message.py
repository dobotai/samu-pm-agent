#!/usr/bin/env python3
"""
End-of-Day Checkout Message — generates Samu's daily status update.

Deterministic script (no LLM API calls). Gathers today's data from Airtable
and outputs a structured checkout message in the SOP template format.

Simon runs this from Claude Code at end of day, copies to Samu.

SOP format (from pm_skills_bible.md):
    Logging off. Status:
    - Completed: [list]
    - In progress: [list]
    - Blocked on: [list]
    No open loops / [specific items need morning attention].

Usage:
    python execution/checkout_message.py
    python execution/checkout_message.py --output json
"""

import os
import sys
import json
import argparse
from datetime import datetime, date, timedelta

from dotenv import load_dotenv
load_dotenv()

# Shared helpers
sys.path.insert(0, os.path.dirname(__file__))
from airtable_read import read_airtable_records

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
from utils import format_video_ref, get_client_map, resolve_editor_name, get_editor_map


# ---------------------------------------------------------------------------
# Status constants (same as editor_task_report)
# ---------------------------------------------------------------------------

MILESTONE_STATUSES = {
    "100 - Scheduled - DONE": "Scheduled",
    "80 - Approved By Client": "Client approved",
    "75 - Sent to Client For Review": "Sent for review",
    "60 - Submitted for QC": "Submitted for QC",
    "60 - Internal Review": "Submitted for QC",
}

ACTIVE_STATUSES = {
    "60 - Submitted for QC": "QC queue",
    "60 - Internal Review": "QC queue",
    "80 - Approved By Client": "Ready to schedule",
    "75 - Sent to Client For Review": "Client review",
    "59 - Editing Revisions": "Revisions",
    "50 - Editor Confirmed": "Editing",
    "41 - Sent to Editor": "Editing",
    "40 - Client Sent Raw Footage": "Awaiting editor",
}


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

def get_todays_milestones(client_map, editor_map):
    """Find videos that hit a milestone today (status changed today).

    Uses Last Modified (Editing Status) to detect changes.
    """
    today_str = date.today().isoformat()

    # Fetch videos in milestone statuses
    milestone_filter = (
        "OR("
        "{Editing Status}='100 - Scheduled - DONE',"
        "{Editing Status}='80 - Approved By Client',"
        "{Editing Status}='75 - Sent to Client For Review',"
        "{Editing Status}='60 - Submitted for QC',"
        "{Editing Status}='60 - Internal Review'"
        ")"
    )
    records = read_airtable_records(
        "Videos",
        filter_formula=milestone_filter,
        fields=[
            "Video Number", "Client", "Editing Status", "Format",
            "Assigned Editor", "Editor's Name",
            "Last Modified (Editing Status)",
        ],
    )

    completions = []
    for r in records:
        fields = r["fields"]
        modified_str = fields.get("Last Modified (Editing Status)", "")
        if not modified_str:
            continue

        try:
            modified_date = datetime.fromisoformat(
                modified_str.replace("Z", "+00:00")
            ).date()
        except (ValueError, TypeError):
            continue

        if str(modified_date) != today_str:
            continue

        status = fields.get("Editing Status", "")
        label = MILESTONE_STATUSES.get(status, status)
        display = format_video_ref(fields, client_map)
        editor = resolve_editor_name(fields, editor_map)

        completions.append({
            "video": display,
            "milestone": label,
            "editor": editor,
            "status": status,
        })

    return completions


def get_pipeline_summary(client_map):
    """Get current active pipeline grouped by status bucket."""
    active_filter = (
        "OR("
        "{Editing Status}='40 - Client Sent Raw Footage',"
        "{Editing Status}='41 - Sent to Editor',"
        "{Editing Status}='50 - Editor Confirmed',"
        "{Editing Status}='59 - Editing Revisions',"
        "{Editing Status}='60 - Submitted for QC',"
        "{Editing Status}='60 - Internal Review',"
        "{Editing Status}='75 - Sent to Client For Review',"
        "{Editing Status}='80 - Approved By Client'"
        ")"
    )
    records = read_airtable_records(
        "Videos",
        filter_formula=active_filter,
        fields=["Video Number", "Client", "Editing Status", "Format"],
    )

    buckets = {}
    for r in records:
        fields = r["fields"]
        status = fields.get("Editing Status", "")
        label = ACTIVE_STATUSES.get(status, "Other")
        buckets.setdefault(label, []).append(format_video_ref(fields, client_map))

    return buckets


def get_attention_items(client_map, editor_map):
    """Find items that need morning attention.

    - Videos waiting on client (75) for 48h+ with no status change
    - Videos in QC (60) — Simon needs to review these
    """
    attention = []

    # Check stale client reviews (75 status, last modified 48h+ ago)
    client_review_records = read_airtable_records(
        "Videos",
        filter_formula="{Editing Status}='75 - Sent to Client For Review'",
        fields=[
            "Video Number", "Client", "Editing Status", "Format",
            "Last Modified (Editing Status)",
        ],
    )

    cutoff = (datetime.now() - timedelta(hours=48)).date()

    for r in client_review_records:
        fields = r["fields"]
        modified_str = fields.get("Last Modified (Editing Status)", "")
        if not modified_str:
            continue

        try:
            modified_date = datetime.fromisoformat(
                modified_str.replace("Z", "+00:00")
            ).date()
        except (ValueError, TypeError):
            continue

        if modified_date <= cutoff:
            days_waiting = (date.today() - modified_date).days
            display = format_video_ref(fields, client_map)
            attention.append({
                "video": display,
                "issue": f"Waiting on client ({days_waiting}d)",
                "type": "client_wait",
            })

    # QC items that Simon needs to review
    qc_records = read_airtable_records(
        "Videos",
        filter_formula="OR({Editing Status}='60 - Submitted for QC', {Editing Status}='60 - Internal Review')",
        fields=[
            "Video Number", "Client", "Editing Status", "Format",
            "Assigned Editor", "Editor's Name",
        ],
    )

    for r in qc_records:
        fields = r["fields"]
        display = format_video_ref(fields, client_map)
        editor = resolve_editor_name(fields, editor_map)
        attention.append({
            "video": display,
            "issue": f"Needs QC (from {editor})",
            "type": "qc_needed",
        })

    return attention


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_checkout(milestones, pipeline, attention):
    """Format everything into the SOP checkout template."""
    lines = []
    today_str = date.today().strftime("%b %d, %Y")
    lines.append(f"## End-of-Day Checkout — {today_str}")
    lines.append("")

    # Completed today
    lines.append("**Completed today:**")
    if milestones:
        for m in milestones:
            editor_note = f" ({m['editor']})" if m["editor"] != "Unassigned" else ""
            lines.append(f"- {m['milestone']}: {m['video']}{editor_note}")
    else:
        lines.append("- No milestone status changes today")
    lines.append("")

    # In progress
    lines.append("**In progress:**")
    # Order: QC first, then scheduling, revisions, client review, editing
    bucket_order = [
        "QC queue", "Ready to schedule", "Revisions",
        "Client review", "Editing", "Awaiting editor",
    ]
    total_active = 0
    for bucket in bucket_order:
        videos = pipeline.get(bucket, [])
        if videos:
            total_active += len(videos)
            if len(videos) <= 3:
                video_list = ", ".join(videos)
                lines.append(f"- {len(videos)} {bucket.lower()}: {video_list}")
            else:
                lines.append(f"- {len(videos)} {bucket.lower()}")
    # Catch any bucket not in our order
    for bucket, videos in pipeline.items():
        if bucket not in bucket_order and videos:
            total_active += len(videos)
            lines.append(f"- {len(videos)} {bucket.lower()}")
    if total_active == 0:
        lines.append("- No active videos")
    lines.append("")

    # Blocked / needs morning attention
    if attention:
        lines.append("**Needs morning attention:**")
        # QC items first, then client waits
        qc_items = [a for a in attention if a["type"] == "qc_needed"]
        wait_items = [a for a in attention if a["type"] == "client_wait"]

        for a in qc_items:
            lines.append(f"- {a['video']} — {a['issue']}")
        for a in wait_items:
            lines.append(f"- {a['video']} — {a['issue']}")
        lines.append("")

    # Summary line
    lines.append("---")
    summary = f"**{total_active} active videos."
    if milestones:
        summary += f" {len(milestones)} milestone{'s' if len(milestones) != 1 else ''} today."
    if attention:
        qc_count = sum(1 for a in attention if a["type"] == "qc_needed")
        wait_count = sum(1 for a in attention if a["type"] == "client_wait")
        parts = []
        if qc_count:
            parts.append(f"{qc_count} QC")
        if wait_count:
            parts.append(f"{wait_count} client follow-up{'s' if wait_count != 1 else ''}")
        if parts:
            summary += f" {' + '.join(parts)} for tomorrow."
    else:
        summary += " No open loops."
    summary += "**"
    lines.append(summary)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate end-of-day checkout message for Samu"
    )
    parser.add_argument(
        "--output",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    args = parser.parse_args()

    try:
        print("Fetching Airtable data...", file=sys.stderr)
        client_map = get_client_map()
        editor_map = get_editor_map()

        print("Checking today's milestones...", file=sys.stderr)
        milestones = get_todays_milestones(client_map, editor_map)

        print("Building pipeline summary...", file=sys.stderr)
        pipeline = get_pipeline_summary(client_map)

        print("Finding attention items...", file=sys.stderr)
        attention = get_attention_items(client_map, editor_map)

        if args.output == "json":
            print(json.dumps({
                "milestones": milestones,
                "pipeline": pipeline,
                "attention": attention,
                "date": date.today().isoformat(),
            }, indent=2))
        else:
            print(format_checkout(milestones, pipeline, attention))

        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
