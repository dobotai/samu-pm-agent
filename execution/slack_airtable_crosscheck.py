#!/usr/bin/env python3
"""
Slack-Airtable Cross-Check Tool
Compares Slack editor channel activity with Airtable status to identify discrepancies.

Three checks:
1. Status discrepancies — Editor says 'done' in Slack but Airtable not updated
2. Communication gaps — Editor channels with active videos but zero messages
3. Client deliverables — Monthly video delivery count vs package commitment

Usage:
    python execution/slack_airtable_crosscheck.py
    python execution/slack_airtable_crosscheck.py --check status
    python execution/slack_airtable_crosscheck.py --check deliverables
    python execution/slack_airtable_crosscheck.py --hours 72
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime, date

from dotenv import load_dotenv
load_dotenv()

# Shared helpers (same pattern as editor_task_report / client_status_report)
sys.path.insert(0, os.path.dirname(__file__))
from airtable_read import read_airtable_records
from slack_read_channel import read_slack_channel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
from utils import format_video_ref, get_client_map, resolve_editor_name, get_editor_map
from constants import (
    QC_STATUSES, POST_DEADLINE_STATUSES, INACTIVE_CLIENT_STATUSES,
    ALL_ACTIVE_STATUSES, STATUS_ORDER, STATUS_STALE_DAYS,
)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def get_active_videos():
    """Fetch active (non-completed) videos with fields needed for crosscheck."""
    return read_airtable_records(
        "Videos",
        filter_formula="AND({Editing Status} != '', FIND('100 -', {Editing Status}) = 0)",
        fields=[
            "Video Number", "Client", "Editing Status", "Format",
            "Assigned Editor", "Editor's Name",
            "Editor's Slack Channel", "Slack ID Channel (from Assigned Editor)",
            "Last Modified (Editing Status)",
        ],
    )


def get_all_videos():
    """Fetch all videos (including completed) for deliverables tracking."""
    return read_airtable_records(
        "Videos",
        fields=[
            "Client", "Editing Status",
            "Last Modified (Editing Status)",
        ],
    )


def get_client_info():
    """Fetch client records with status and deliverables."""
    records = read_airtable_records("Clients", fields=["Name", "Status", "Deliverables"])
    return {
        r["id"]: {
            "name": r["fields"].get("Name", "Unknown"),
            "status": r["fields"].get("Status", ""),
            "deliverables": r["fields"].get("Deliverables", ""),
        }
        for r in records
    }


# ---------------------------------------------------------------------------
# Check 1: Status discrepancies
# ---------------------------------------------------------------------------

# Completion keywords — must be specific to avoid false positives.
# "sent" alone matches "sent the footage" (client uploading, not editor finishing).
# "ready" alone matches "ready to start" (not completion).
COMPLETION_KEYWORDS = [
    "done", "finished", "completed", "uploaded", "delivered",
    "sent for review", "submitted for qc", "ready for review",
    "ready for qc", "ready for checking",
]


def check_status_discrepancies(active_videos, client_map, editor_map, hours=48):
    """Find videos where Slack mentions completion but Airtable status is behind."""
    # Group videos by editor channel to minimize Slack API calls
    channel_videos = {}
    for v in active_videos:
        fields = v["fields"]
        status = fields.get("Editing Status", "")

        # Skip statuses already past editing (sent to client, approved, done)
        skip_statuses = POST_DEADLINE_STATUSES + ["75 - Sent to Client For Review"]
        if status in skip_statuses:
            continue

        channel_ids = (
            fields.get("Editor's Slack Channel", [])
            or fields.get("Slack ID Channel (from Assigned Editor)", [])
        )
        if not channel_ids:
            continue

        ch_id = channel_ids[0] if isinstance(channel_ids, list) else channel_ids
        channel_videos.setdefault(ch_id, []).append(v)

    # Keywords that CONFIRM a QC status (not contradict it)
    QC_CONSISTENT_KEYWORDS = {
        "ready for review", "submitted for qc",
        "ready for qc", "ready for checking",
    }

    discrepancies = []

    def _check_msg_for_discrepancy(msg, display_name, editor, status,
                                    client_name, video_num):
        """Check a single message (top-level or thread reply) for completion keywords."""
        # Skip Airtable bot messages
        sender = msg.get("user", "").lower()
        username = msg.get("username", "")
        if sender == "airtable" or "airtable" in str(username).lower():
            return

        text = msg.get("text", "").lower()

        # Require BOTH client name AND video number to avoid false positives
        has_client = client_name and client_name.lower() in text
        has_num = video_num and (
            f"#{video_num}" in text
            or f"video {video_num}" in text
            or f"video #{video_num}" in text
            or f"{client_name.lower()}{video_num}" in text
        )
        if not (has_client and has_num):
            return

        for keyword in COMPLETION_KEYWORDS:
            if keyword in text:
                if keyword in QC_CONSISTENT_KEYWORDS and status in QC_STATUSES:
                    break
                msg_time = msg.get("datetime", "")
                discrepancies.append({
                    "video": display_name,
                    "editor": editor,
                    "airtable_status": status,
                    "slack_says": msg.get("text", "")[:120],
                    "when": msg_time,
                    "issue": f"Slack mentions '{keyword}' but Airtable is '{status}'",
                })
                break

    for ch_id, videos in channel_videos.items():
        # Read channel messages once per channel (with threads)
        try:
            messages = read_slack_channel(ch_id, since_hours=hours, include_threads=True, max_threads=20)
        except Exception:
            continue

        if not messages:
            continue

        for v in videos:
            fields = v["fields"]
            display_name = format_video_ref(fields, client_map)
            editor = resolve_editor_name(fields, editor_map)
            status = fields.get("Editing Status", "")
            video_num = str(fields.get("Video Number", ""))

            client_ids = fields.get("Client", [])
            client_name = ""
            if client_ids and client_map:
                cid = client_ids[0] if isinstance(client_ids, list) else client_ids
                client_name = client_map.get(cid, "")

            for msg in messages:
                _check_msg_for_discrepancy(
                    msg, display_name, editor, status, client_name, video_num
                )
                # Also check thread replies
                for reply in msg.get("thread_replies", []):
                    _check_msg_for_discrepancy(
                        reply, display_name, editor, status, client_name, video_num
                    )

    return discrepancies


# ---------------------------------------------------------------------------
# Check 2: Communication gaps
# ---------------------------------------------------------------------------

def check_communication_gaps(active_videos, client_map, editor_map, hours=72):
    """Find editor channels with active videos but zero messages."""
    # Group active videos by editor channel
    channel_videos = {}
    for v in active_videos:
        fields = v["fields"]
        status = fields.get("Editing Status", "")

        # Only check videos currently with editors (not sent to client / approved / done)
        skip_statuses = POST_DEADLINE_STATUSES + ["75 - Sent to Client For Review"]
        if status in skip_statuses:
            continue

        channel_ids = (
            fields.get("Editor's Slack Channel", [])
            or fields.get("Slack ID Channel (from Assigned Editor)", [])
        )
        if not channel_ids:
            continue

        ch_id = channel_ids[0] if isinstance(channel_ids, list) else channel_ids
        channel_videos.setdefault(ch_id, []).append(v)

    gaps = []

    for ch_id, videos in channel_videos.items():
        try:
            messages = read_slack_channel(ch_id, since_hours=hours, include_threads=True, max_threads=10)
        except Exception:
            messages = []

        # Count total activity including thread replies
        has_activity = bool(messages) or any(
            msg.get("thread_replies") for msg in (messages or [])
        )
        if not has_activity:
            editor = resolve_editor_name(videos[0]["fields"], editor_map)
            video_refs = [format_video_ref(v["fields"], client_map) for v in videos]
            gaps.append({
                "editor": editor,
                "active_videos": video_refs,
                "video_count": len(videos),
                "silent_hours": hours,
            })

    return gaps


# ---------------------------------------------------------------------------
# Check 3: Client deliverables
# ---------------------------------------------------------------------------

def _parse_deliverables(raw_str):
    """Parse a deliverables string into structured counts.

    Handles compound packages:
        "4 long-form + 2 shorts" -> {long_form: 4, shorts: 2, total: 6}
        "6/mo"                   -> {long_form: 6, shorts: 0, total: 6}
        "4 long-form"            -> {long_form: 4, shorts: 0, total: 4}
        "8"                      -> {long_form: 8, shorts: 0, total: 8}
    """
    if not raw_str:
        return {"long_form": 0, "shorts": 0, "total": 0}

    text = str(raw_str).lower()
    # Remove resolution numbers (720p, 1080p, 2160p, 4k)
    text = re.sub(r"\b(720|1080|2160|4k)\w*", "", text)

    long_form = 0
    shorts = 0

    # Try to find "X shorts" or "X short-form"
    shorts_match = re.search(r"(\d+)\s*(?:short|shorts|short-form)", text)
    if shorts_match:
        shorts = int(shorts_match.group(1))

    # Try to find "X long-form" or "X long" or "X videos" or "X/mo"
    long_match = re.search(r"(\d+)\s*(?:long-form|long|videos?|/mo)", text)
    if long_match:
        long_form = int(long_match.group(1))
    elif not shorts_match:
        # Fallback: just grab the first number
        nums = re.findall(r"\d+", text)
        if nums:
            long_form = int(nums[0])

    total = long_form + shorts
    return {"long_form": long_form, "shorts": shorts, "total": total}


def check_client_deliverables(all_videos, client_info):
    """Compare monthly video delivery counts against package commitments."""
    today = date.today()
    first_of_month = today.replace(day=1)

    client_counts = {}

    for v in all_videos:
        fields = v["fields"]
        status = fields.get("Editing Status", "")
        client_ids = fields.get("Client", [])
        if not client_ids:
            continue

        cid = client_ids[0] if isinstance(client_ids, list) else client_ids
        info = client_info.get(cid)
        if not info:
            continue

        # Only track active clients
        if info["status"] in INACTIVE_CLIENT_STATUSES:
            continue

        name = info["name"]
        if name not in client_counts:
            client_counts[name] = {
                "delivered": 0,
                "active": 0,
                "deliverables_raw": info.get("deliverables", ""),
            }

        # Count active (non-completed)
        if status and "100 -" not in status and "DONE" not in status:
            client_counts[name]["active"] += 1

        # Count delivered this month
        if "100 -" in status or "DONE" in status:
            modified_str = fields.get("Last Modified (Editing Status)", "")
            if modified_str:
                try:
                    modified_date = datetime.fromisoformat(
                        modified_str.replace("Z", "+00:00")
                    ).date()
                    if modified_date >= first_of_month:
                        client_counts[name]["delivered"] += 1
                except (ValueError, TypeError):
                    pass

    # Parse deliverables targets and build results
    results = []
    for name, counts in sorted(client_counts.items()):
        parsed = _parse_deliverables(counts["deliverables_raw"])
        package_total = parsed["total"]

        # Display format: "4LF+2S/mo" or "6/mo" or "?"
        if parsed["shorts"] > 0:
            package_str = f"{parsed['long_form']}LF+{parsed['shorts']}S/mo"
        elif package_total > 0:
            package_str = f"{package_total}/mo"
        else:
            package_str = "?"

        delivered = counts["delivered"]
        remaining = max(0, package_total - delivered) if package_total > 0 else 0

        results.append({
            "client": name,
            "package": package_str,
            "package_total": package_total,
            "delivered": delivered,
            "active": counts["active"],
            "remaining": remaining,
            "on_track": delivered >= package_total if package_total > 0 else None,
        })

    return results


# ---------------------------------------------------------------------------
# Check 4: Stale statuses
# ---------------------------------------------------------------------------

def check_stale_statuses(active_videos, client_map, editor_map):
    """Find videos stuck at the same status for too long.

    Uses STATUS_STALE_DAYS thresholds from constants.py.
    Returns list of {video, editor, status, days_stuck, threshold}.
    """
    stale = []
    now = datetime.now()

    for v in active_videos:
        fields = v["fields"]
        status = fields.get("Editing Status", "")
        threshold = STATUS_STALE_DAYS.get(status)
        if not threshold:
            continue

        lm = fields.get("Last Modified (Editing Status)", "")
        if not lm:
            continue

        try:
            modified_dt = datetime.fromisoformat(lm.replace("Z", "+00:00"))
            days_stuck = (now.astimezone(modified_dt.tzinfo) - modified_dt).days
        except (ValueError, TypeError):
            continue

        if days_stuck >= threshold:
            stale.append({
                "video": format_video_ref(fields, client_map),
                "editor": resolve_editor_name(fields, editor_map),
                "status": status.split(" - ", 1)[-1] if " - " in status else status,
                "days_stuck": days_stuck,
                "threshold": threshold,
            })

    stale.sort(key=lambda s: -s["days_stuck"])
    return stale


# ---------------------------------------------------------------------------
# Check 5: Assignment gaps
# ---------------------------------------------------------------------------

def check_assignment_gaps(deliverables_results):
    """Find clients with remaining deliverables but zero active videos.

    Uses the output of check_client_deliverables.
    Returns list of {client, remaining, package}.
    """
    gaps = []
    for d in deliverables_results:
        if d["remaining"] > 0 and d["active"] == 0:
            gaps.append({
                "client": d["client"],
                "remaining": d["remaining"],
                "package": d["package"],
            })
    return gaps


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def format_markdown_report(results, hours):
    """Format all check results as markdown tables."""
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append("## Crosscheck Report")
    lines.append(f"Generated: {now} | Lookback: {hours}h")
    lines.append("")

    # Status discrepancies
    if "status_discrepancies" in results:
        items = results["status_discrepancies"]
        lines.append(f"### Status Discrepancies ({len(items)} found)")
        if items:
            lines.append("| Video | Editor | Airtable Status | Slack Says | When |")
            lines.append("|-------|--------|----------------|------------|------|")
            for d in items:
                slack_preview = d["slack_says"][:60].replace("|", "/")
                lines.append(
                    f"| {d['video']} | {d['editor']} | {d['airtable_status']} "
                    f"| \"{slack_preview}\" | {d['when'][:16]} |"
                )
        else:
            lines.append("All statuses in sync.")
        lines.append("")

    # Communication gaps
    if "communication_gaps" in results:
        items = results["communication_gaps"]
        lines.append(f"### Communication Gaps ({len(items)} found)")
        if items:
            lines.append("| Editor | Active Videos | Silent For |")
            lines.append("|--------|--------------|------------|")
            for g in items:
                vids = ", ".join(g["active_videos"][:3])
                if len(g["active_videos"]) > 3:
                    vids += f" +{len(g['active_videos']) - 3}"
                lines.append(f"| {g['editor']} | {vids} | {g['silent_hours']}h+ |")
        else:
            lines.append("All editor channels have recent activity.")
        lines.append("")

    # Stale statuses
    if "stale_statuses" in results:
        items = results["stale_statuses"]
        lines.append(f"### Stale Statuses ({len(items)} found)")
        if items:
            lines.append("| Video | Editor | Status | Days Stuck | Expected |")
            lines.append("|-------|--------|--------|-----------|----------|")
            for s in items:
                lines.append(
                    f"| {s['video']} | {s['editor']} | {s['status']} "
                    f"| {s['days_stuck']}d | <{s['threshold']}d |"
                )
        else:
            lines.append("No stale statuses found.")
        lines.append("")

    # Assignment gaps
    if "assignment_gaps" in results and results["assignment_gaps"]:
        gaps = results["assignment_gaps"]
        lines.append(f"### Assignment Gaps ({len(gaps)} clients)")
        lines.append("Need videos assigned to meet monthly package:")
        for g in gaps:
            lines.append(f"- **{g['client']}** -- {g['remaining']} remaining of {g['package']}, 0 active")
        lines.append("")

    # Recommended Actions
    recommendations = []
    if results.get("status_discrepancies"):
        n = len(results["status_discrepancies"])
        recommendations.append(f"Update Airtable for {n} discrepant video{'s' if n != 1 else ''}")
    if results.get("communication_gaps"):
        n = len(results["communication_gaps"])
        recommendations.append(f"Follow up with {n} silent editor{'s' if n != 1 else ''}")
    if results.get("stale_statuses"):
        n = len(results["stale_statuses"])
        recommendations.append(f"Check {n} stale video{'s' if n != 1 else ''}")
    if results.get("assignment_gaps"):
        n = len(results["assignment_gaps"])
        recommendations.append(f"Assign videos for {n} client{'s' if n != 1 else ''} behind on deliverables")

    if recommendations:
        lines.append("### Recommended Actions")
        for i, r in enumerate(recommendations, 1):
            lines.append(f"{i}. {r}")
        lines.append("")

    # Summary line
    lines.append("---")
    summary_parts = []
    if "status_discrepancies" in results:
        n = len(results["status_discrepancies"])
        summary_parts.append(f"{n} discrepanc{'y' if n == 1 else 'ies'} found")
    if "communication_gaps" in results:
        n = len(results["communication_gaps"])
        summary_parts.append(f"{n} editor{'s' if n != 1 else ''} silent")
    if "stale_statuses" in results:
        n = len(results["stale_statuses"])
        summary_parts.append(f"{n} stale status{'es' if n != 1 else ''}")
    if results.get("assignment_gaps"):
        n = len(results["assignment_gaps"])
        summary_parts.append(f"{n} client{'s' if n != 1 else ''} need assignments")
    if summary_parts:
        lines.append(f"**{'. '.join(summary_parts)}.**")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cross-check Slack and Airtable data")
    parser.add_argument(
        "--check",
        choices=["all", "status", "gaps", "stale", "deliverables"],
        default="all",
        help="Type of check to run (default: all)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=48,
        help="Hours to look back for Slack activity (default: 48)",
    )
    parser.add_argument(
        "--output",
        choices=["json", "markdown"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    args = parser.parse_args()

    try:
        # Phase 1: Airtable data
        print("Phase 1: Fetching Airtable data...", file=sys.stderr)
        client_map = get_client_map()
        editor_map = get_editor_map()
        client_info = get_client_info()
        active_videos = get_active_videos()

        results = {}

        # Phase 2: Run checks
        if args.check in ("all", "status"):
            print("Phase 2: Checking status discrepancies...", file=sys.stderr)
            results["status_discrepancies"] = check_status_discrepancies(
                active_videos, client_map, editor_map, args.hours
            )

        if args.check in ("all", "gaps"):
            print("Phase 2: Checking communication gaps...", file=sys.stderr)
            results["communication_gaps"] = check_communication_gaps(
                active_videos, client_map, editor_map, args.hours
            )

        if args.check in ("all", "stale"):
            print("Phase 2: Checking stale statuses...", file=sys.stderr)
            results["stale_statuses"] = check_stale_statuses(
                active_videos, client_map, editor_map
            )

        if args.check in ("all", "deliverables"):
            print("Phase 2: Checking client deliverables...", file=sys.stderr)
            all_videos = get_all_videos()
            results["client_deliverables"] = check_client_deliverables(
                all_videos, client_info
            )
            # Assignment gaps depend on deliverables results
            results["assignment_gaps"] = check_assignment_gaps(
                results["client_deliverables"]
            )

        # Phase 3: Output
        if args.output == "json":
            print(json.dumps(results, indent=2))
        else:
            print(format_markdown_report(results, args.hours))

        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
