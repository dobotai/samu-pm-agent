#!/usr/bin/env python3
"""
End-of-Day Checkout Message — generates Simon's checkout update for Samu.

Deterministic script (no LLM API calls). Gathers today's data from Airtable
and outputs a checkout message matching the real #project-management format.

Simon runs this from Claude Code at end of day, edits [fill in] sections,
then copies to #project-management.

Real format (from Slack):
    Here's my Check Out Message:
    * QCs- cleared dan16, fibbler9. omeed13, smartlead1 still pending
    * Scheduled videos- scheduled arborxr14, jamal1+2. adampod23 needs scheduling
    * Videos sent to client for review- dan16, emailchaser7, fibbler9
    * Clients followed up with recording- need recording from X, Y, Z
    * Close deadlines- omeed13 deadline is today, in QC
    * Additional tasks- [fill in]
    * Reminders leftover- [fill in]
    * Mistakes sheet
    * Social Posts Completed
    I'm starting tomorrow at the usual time!

Usage:
    python execution/checkout_message.py
    python execution/checkout_message.py --output json
"""

import io
import os
import sys
import json
import re
import argparse
from datetime import datetime, date, timedelta
from collections import OrderedDict

from dotenv import load_dotenv
load_dotenv()

# Shared helpers
sys.path.insert(0, os.path.dirname(__file__))
from airtable_read import read_airtable_records
from constants import (
    QC_STATUSES, INACTIVE_CLIENT_STATUSES, POST_DEADLINE_STATUSES,
    SIMON_SLACK_USER_ID,
)
from slack_read_channel import read_slack_channel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
from utils import format_video_ref, resolve_editor_name


# ---------------------------------------------------------------------------
# Compact video ref formatting
# ---------------------------------------------------------------------------

# Max days overdue to show in Close Deadlines (older = stale, skip)
OVERDUE_CUTOFF_DAYS = 3


def _clean_client_name(name):
    """Lowercase client name, strip spaces and parens.

    'Jeremy (Coco AI)' → 'jeremycocoai'
    'Force Equals'     → 'forceequals'
    'ArborXR'          → 'arborxr'
    """
    return re.sub(r'[() ]', '', name.lower())


def _compact_ref(client_name, video_num, is_shorts=False):
    """Generate a single compact video ref.

    Pure numbers:     'Dan', '16', False  → 'dan16'
    Shorts number:    'Dan', '3', True    → 'dan shorts 3'
    VidX Shorts:      'Dan', 'Vid15 Shorts' → 'dan shorts 15'
    PodX Shorts:      'Hiver', 'Pod5 Shorts' → 'hiver pod shorts 5'
    Podcast:          'Adam', 'podcast 23'   → 'adam pod23'
    Complex (Wassia): 'Wassia', 'Vid4LF2'   → 'wassia vid4lf2'
    VSL:              'Taylor', 'CEI VSL'    → 'taylor CEI VSL'
    """
    name = _clean_client_name(client_name)
    vnum = str(video_num).strip()

    # "Vid15 Shorts" → shorts 15
    m = re.match(r'^Vid(\d+)\s*Shorts$', vnum, re.IGNORECASE)
    if m:
        return f"{name} shorts {m.group(1)}"

    # "Pod5 Shorts" → pod shorts 5
    m = re.match(r'^Pod(\d+)\s*Shorts$', vnum, re.IGNORECASE)
    if m:
        return f"{name} pod shorts {m.group(1)}"

    # "Podcast 23" or "podcast 23" → pod23
    m = re.match(r'^[Pp]odcast\s*(\d+)$', vnum)
    if m:
        return f"{name} pod{m.group(1)}"

    # Pure number (most common)
    if re.match(r'^\d+$', vnum):
        if is_shorts:
            return f"{name} shorts {vnum}"
        return f"{name}{vnum}"

    # Complex/descriptive (VSL, VidXLFY, etc.) — keep readable
    return f"{name} {vnum}"


def _group_compact(items):
    """Group video items by client for compact display.

    Pure-number videos from the same client get grouped: dan14+16, ocuco2+3
    Complex video numbers stay individual: wassia vid4lf2, taylor CEI VSL
    """
    # Separate groupable (pure number) from ungroupable (complex)
    groupable = OrderedDict()  # (clean_name, is_shorts) → [num_str, ...]
    ungroupable = []

    for item in items:
        vnum = str(item["video_num"]).strip()
        is_shorts = item.get("is_shorts", False)

        if re.match(r'^\d+$', vnum):
            key = (_clean_client_name(item["client_name"]), is_shorts)
            groupable.setdefault(key, []).append(vnum)
        else:
            ungroupable.append(item)

    parts = []

    # Grouped items: dan14+16, ocuco2+3
    for (name, is_shorts), nums in groupable.items():
        nums.sort(key=lambda n: int(n))
        joined = "+".join(nums)
        if is_shorts:
            parts.append(f"{name} shorts {joined}")
        else:
            parts.append(f"{name}{joined}")

    # Ungroupable items: compact ref each individually
    for item in ungroupable:
        parts.append(_compact_ref(
            item["client_name"], item["video_num"], item.get("is_shorts", False)
        ))

    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Client/editor maps (with inactive filtering)
# ---------------------------------------------------------------------------

def _load_client_data():
    """Fetch clients with status info for inactive filtering."""
    clients_raw = read_airtable_records("Clients", fields=["Name", "Status"])
    client_map = {r["id"]: r["fields"].get("Name", "?") for r in clients_raw}
    inactive_clients = {
        r["fields"].get("Name", "").lower()
        for r in clients_raw
        if r["fields"].get("Status", "") in INACTIVE_CLIENT_STATUSES
    }
    return client_map, inactive_clients


def _load_editor_map():
    """Fetch team table -> {record_id: name}."""
    records = read_airtable_records("Team", fields=["Name"])
    return {r["id"]: r["fields"].get("Name", "Unknown") for r in records}


def _is_inactive(fields, client_map, inactive_clients):
    """Check if a video belongs to an inactive client."""
    client_ids = fields.get("Client", [])
    if client_ids:
        cid = client_ids[0] if isinstance(client_ids, list) else client_ids
        name = client_map.get(cid, "")
        return name.lower() in inactive_clients
    return False


def _resolve_client_name(fields, client_map):
    """Get client name from video fields."""
    client_ids = fields.get("Client", [])
    if client_ids:
        cid = client_ids[0] if isinstance(client_ids, list) else client_ids
        return client_map.get(cid, "Unknown")
    return "Unknown"


def _extract_video_info(fields, client_map, editor_map=None):
    """Extract structured video info for compact formatting."""
    client_name = _resolve_client_name(fields, client_map)
    video_num = str(fields.get("Video Number", "?"))
    fmt = str(fields.get("Format", "")).lower()
    is_shorts = "short" in fmt
    editor = resolve_editor_name(fields, editor_map) if editor_map else "Unassigned"
    return {
        "client_name": client_name,
        "video_num": video_num,
        "is_shorts": is_shorts,
        "editor": editor,
        "full_ref": format_video_ref(fields, client_map),
    }


# ---------------------------------------------------------------------------
# PM activity detection (Slack scan of #project-management)
# ---------------------------------------------------------------------------

def get_todays_pm_activity():
    """Read Simon's messages in #project-management today.

    Detects already-reported activities (scheduling, QC, sends to client).
    Returns: {"scheduled": [refs], "sent_to_client": [refs], "qc_cleared": [refs]}
    """
    result = {"scheduled": [], "sent_to_client": [], "qc_cleared": []}

    try:
        messages = read_slack_channel(
            "#project-management", limit=50, since_hours=12,
            include_threads=False
        )
    except Exception:
        return result

    for msg in messages:
        if msg.get("user_id") != SIMON_SLACK_USER_ID:
            continue
        text = msg.get("text", "").lower()
        if not text:
            continue

        # Detect scheduling mentions
        if "scheduled" in text or "scheduling" in text:
            result["scheduled"].append(text[:100])
        # Detect client sends
        if ("sent to" in text and "client" in text) or "sent for review" in text:
            result["sent_to_client"].append(text[:100])
        # Detect QC clears
        if "qc" in text and ("cleared" in text or "done" in text or "approved" in text):
            result["qc_cleared"].append(text[:100])

    return result


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

def get_todays_milestones(client_map, inactive_clients, editor_map):
    """Find videos that hit a milestone today (status changed today)."""
    today_str = date.today().isoformat()

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

    milestones = []
    for r in records:
        fields = r["fields"]
        if _is_inactive(fields, client_map, inactive_clients):
            continue

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
        info = _extract_video_info(fields, client_map, editor_map)
        info["status"] = status
        milestones.append(info)

    return milestones


def get_current_qc_queue(client_map, inactive_clients, editor_map):
    """Videos currently pending QC (status 60)."""
    qc_filter = "OR({Editing Status}='60 - Submitted for QC', {Editing Status}='60 - Internal Review')"
    records = read_airtable_records(
        "Videos",
        filter_formula=qc_filter,
        fields=[
            "Video Number", "Client", "Editing Status", "Format",
            "Assigned Editor", "Editor's Name",
        ],
    )
    items = []
    for r in records:
        fields = r["fields"]
        if _is_inactive(fields, client_map, inactive_clients):
            continue
        items.append(_extract_video_info(fields, client_map, editor_map))
    return items


def get_ready_to_schedule(client_map, inactive_clients):
    """Videos approved by client (status 80) — need YouTube scheduling."""
    records = read_airtable_records(
        "Videos",
        filter_formula="{Editing Status}='80 - Approved By Client'",
        fields=["Video Number", "Client", "Editing Status", "Format"],
    )
    items = []
    for r in records:
        fields = r["fields"]
        if _is_inactive(fields, client_map, inactive_clients):
            continue
        items.append(_extract_video_info(fields, client_map))
    return items


def get_upcoming_deadlines(client_map, inactive_clients, editor_map, days_ahead=2):
    """Videos with actionable close deadlines.

    Args:
        days_ahead: How many days to look ahead (default: 2, use 4 for Fridays).

    Filters for deadlines Simon can act on:
    - 41/50 (with editor, V1 not delivered): today through +days_ahead, plus 1d overdue
    - 59 (revisions): today/tomorrow only (V1 was delivered, revs expected late)
    - 60 (QC): today/tomorrow only (Simon needs to act)
    - 75 (with client): excluded entirely — we can't control client timing

    Per SOP: deadline = V1 delivery date. Videos past deadline in revision
    cycles (59/60/75) are normal. Only flag if genuinely actionable.
    """
    active_filter = (
        "OR("
        "{Editing Status}='41 - Sent to Editor',"
        "{Editing Status}='50 - Editor Confirmed',"
        "{Editing Status}='59 - Editing Revisions',"
        "{Editing Status}='60 - Submitted for QC',"
        "{Editing Status}='60 - Internal Review'"
        ")"
    )
    records = read_airtable_records(
        "Videos",
        filter_formula=active_filter,
        fields=[
            "Video Number", "Client", "Editing Status", "Format",
            "Assigned Editor", "Editor's Name", "Deadline",
        ],
    )

    today = date.today()

    status_labels = {
        "41 - Sent to Editor": "with editor",
        "50 - Editor Confirmed": "editing",
        "59 - Editing Revisions": "on revs",
        "60 - Submitted for QC": "in QC",
        "60 - Internal Review": "in QC",
    }

    upcoming = []
    for r in records:
        fields = r["fields"]
        if _is_inactive(fields, client_map, inactive_clients):
            continue

        deadline_str = fields.get("Deadline", "")
        if not deadline_str:
            continue

        try:
            dl = datetime.strptime(deadline_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        days_until = (dl - today).days
        status = fields.get("Editing Status", "")

        # Per-status deadline windows:
        # V1 not delivered (41/50): show -1d to +2d (editor needs to deliver)
        # Revisions (59): today/tomorrow only (V1 done, rev cycle is normal)
        # QC (60): today/tomorrow only (Simon needs to review)
        if status in ("41 - Sent to Editor", "50 - Editor Confirmed"):
            if days_until < -1 or days_until > 2:
                continue
        else:
            # 59, 60 statuses
            if days_until < 0 or days_until > 1:
                continue

        if days_until < 0:
            when = f"was {abs(days_until)}d ago"
        elif days_until == 0:
            when = "is today"
        elif days_until == 1:
            when = "is tomorrow"
        else:
            when = f"in {days_until}d"

        info = _extract_video_info(fields, client_map, editor_map)
        info["deadline_when"] = when
        info["status_short"] = status_labels.get(status, status)
        info["days_until"] = days_until
        upcoming.append(info)

    upcoming.sort(key=lambda x: x["days_until"])
    return upcoming


def get_recording_needed(client_map, inactive_clients):
    """Clients we're waiting on to send recording/footage.

    Returns: OrderedDict {client_name: {"videos": [...], "days_waiting": int}}
    days_waiting = days since oldest video entered this status.
    """
    rec_filter = "{Editing Status}='Waiting For Input From Client'"
    records = read_airtable_records(
        "Videos",
        filter_formula=rec_filter,
        fields=[
            "Video Number", "Client", "Editing Status", "Format",
            "Last Modified (Editing Status)",
        ],
    )

    by_client = OrderedDict()
    today = date.today()

    for r in records:
        fields = r["fields"]
        if _is_inactive(fields, client_map, inactive_clients):
            continue
        client_name = _resolve_client_name(fields, client_map)
        info = _extract_video_info(fields, client_map)

        # Calculate days waiting from Last Modified
        lm = fields.get("Last Modified (Editing Status)", "")
        days_w = None
        if lm:
            try:
                lm_date = datetime.fromisoformat(lm.replace("Z", "+00:00")).date()
                days_w = (today - lm_date).days
            except (ValueError, TypeError):
                pass
        info["days_waiting"] = days_w

        entry = by_client.setdefault(client_name, {"videos": [], "days_waiting": None})
        entry["videos"].append(info)
        # Track the oldest (max) days_waiting across all videos for this client
        if days_w is not None:
            if entry["days_waiting"] is None or days_w > entry["days_waiting"]:
                entry["days_waiting"] = days_w

    return by_client


# ---------------------------------------------------------------------------
# Formatting — matches real #project-management checkout format
# ---------------------------------------------------------------------------

def format_checkout(milestones, qc_queue, ready_to_schedule,
                    deadlines, recording_needed, pm_activity=None):
    """Format checkout message matching real Slack format.

    Uses * bullet + section header + dash + content on one line.
    Auto-fills from Airtable, [fill in] for manual sections.
    pm_activity: dict from get_todays_pm_activity() with already-done items.
    """
    pm_activity = pm_activity or {"scheduled": [], "sent_to_client": [], "qc_cleared": []}
    lines = []
    lines.append("Here's my Check Out Message:")

    # --- QCs ---
    # Videos sent to client today (75) = QC was done on them
    qcd_today = [m for m in milestones if m["status"] == "75 - Sent to Client For Review"]
    qc_parts = []
    if qcd_today:
        qc_parts.append(f"cleared {_group_compact(qcd_today)}")
    if qc_queue:
        qc_parts.append(f"{_group_compact(qc_queue)} still pending")
    if not qc_parts:
        if pm_activity["qc_cleared"]:
            qc_parts.append("qcs all cleared (confirmed in #pm)")
        else:
            qc_parts.append("qcs all cleared")
    elif not qc_queue:
        qc_parts.append("all cleared")
    lines.append(f"* QCs- {'. '.join(qc_parts)}")

    # --- Scheduled videos ---
    sched_parts = []
    scheduled_today = [m for m in milestones if m["status"] == "100 - Scheduled - DONE"]
    if scheduled_today:
        sched_parts.append(f"scheduled {_group_compact(scheduled_today)}")
    if ready_to_schedule:
        sched_parts.append(f"{_group_compact(ready_to_schedule)} needs scheduling")
    if not sched_parts:
        if pm_activity["scheduled"]:
            sched_parts.append("all scheduled (confirmed in #pm)")
        else:
            sched_parts.append("all scheduled")
    lines.append(f"* Scheduled videos- {'. '.join(sched_parts)}")

    # --- Videos sent to client for review ---
    sent_today = [m for m in milestones if m["status"] == "75 - Sent to Client For Review"]
    if sent_today:
        lines.append(f"* Videos sent to client for review- {_group_compact(sent_today)}")
    else:
        lines.append("* Videos sent to client for review- nothing new sent today")

    # --- Clients followed up with recording ---
    if recording_needed:
        parts = []
        for name, data in recording_needed.items():
            days_w = data.get("days_waiting")
            if days_w is not None and days_w > 0:
                parts.append(f"{name.lower()} ({days_w}d)")
            else:
                parts.append(name.lower())
        lines.append(
            f"* Clients followed up with recording- need recording from "
            f"{', '.join(parts)} [edit follow-up status]"
        )
    else:
        lines.append("* Clients followed up with recording- no recordings pending")

    # --- Close deadlines ---
    if deadlines:
        dl_parts = []
        for d in deadlines:
            ref = _compact_ref(d["client_name"], d["video_num"], d.get("is_shorts", False))
            dl_parts.append(f"{ref} deadline {d['deadline_when']}, {d['status_short']}")
        lines.append(f"* Close deadlines- {', '.join(dl_parts)}")
    else:
        lines.append("* Close deadlines- no close deadlines")

    # --- Additional tasks (manual) ---
    lines.append("* Additional tasks- [fill in]")

    # --- Reminders leftover (manual) ---
    lines.append("* Reminders leftover- [fill in]")

    # --- Mistakes sheet (manual) ---
    lines.append("* Mistakes sheet")

    # --- Social Posts Completed (manual) ---
    lines.append("* Social Posts Completed")

    # --- Sign off ---
    lines.append("I'm starting tomorrow at the usual time!")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Force UTF-8 stdout on Windows to prevent encoding errors
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="Generate end-of-day checkout message for Samu"
    )
    parser.add_argument(
        "--output",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=2,
        help="Deadline lookahead window in days (default: 2, use 4 for Fridays)",
    )

    args = parser.parse_args()

    try:
        print("Fetching Airtable data...", file=sys.stderr)
        client_map, inactive_clients = _load_client_data()
        editor_map = _load_editor_map()

        print("Checking today's milestones...", file=sys.stderr)
        try:
            milestones = get_todays_milestones(client_map, inactive_clients, editor_map)
        except Exception as e:
            print(f"  Warning: milestones fetch failed: {e}", file=sys.stderr)
            milestones = []

        print("Checking QC queue...", file=sys.stderr)
        try:
            qc_queue = get_current_qc_queue(client_map, inactive_clients, editor_map)
        except Exception as e:
            print(f"  Warning: QC queue fetch failed: {e}", file=sys.stderr)
            qc_queue = []

        print("Checking scheduling queue...", file=sys.stderr)
        try:
            ready_to_schedule = get_ready_to_schedule(client_map, inactive_clients)
        except Exception as e:
            print(f"  Warning: scheduling queue fetch failed: {e}", file=sys.stderr)
            ready_to_schedule = []

        print("Checking deadlines...", file=sys.stderr)
        try:
            deadlines = get_upcoming_deadlines(client_map, inactive_clients, editor_map, days_ahead=args.days)
        except Exception as e:
            print(f"  Warning: deadlines fetch failed: {e}", file=sys.stderr)
            deadlines = []

        print("Checking recording needs...", file=sys.stderr)
        try:
            recording_needed = get_recording_needed(client_map, inactive_clients)
        except Exception as e:
            print(f"  Warning: recording needs fetch failed: {e}", file=sys.stderr)
            recording_needed = {}

        print("Scanning #project-management for today's activity...", file=sys.stderr)
        try:
            pm_activity = get_todays_pm_activity()
        except Exception as e:
            print(f"  Warning: PM activity scan failed: {e}", file=sys.stderr)
            pm_activity = {"scheduled": [], "sent_to_client": [], "qc_cleared": []}

        if args.output == "json":
            print(json.dumps({
                "milestones": milestones,
                "qc_queue": qc_queue,
                "ready_to_schedule": ready_to_schedule,
                "deadlines": deadlines,
                "recording_needed": {
                    k: {
                        "videos": [v["full_ref"] for v in data["videos"]],
                        "days_waiting": data["days_waiting"],
                    }
                    for k, data in recording_needed.items()
                },
                "date": date.today().isoformat(),
            }, indent=2))
        else:
            print(format_checkout(
                milestones, qc_queue, ready_to_schedule,
                deadlines, recording_needed, pm_activity,
            ))

        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
