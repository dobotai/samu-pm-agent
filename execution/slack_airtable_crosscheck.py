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

COMPLETION_KEYWORDS = ["done", "finished", "completed", "uploaded", "sent", "delivered", "ready"]


def check_status_discrepancies(active_videos, client_map, editor_map, hours=48):
    """Find videos where Slack mentions completion but Airtable status is behind."""
    # Group videos by editor channel to minimize Slack API calls
    channel_videos = {}
    for v in active_videos:
        fields = v["fields"]
        status = fields.get("Editing Status", "")

        # Skip statuses already past editing (sent to client, approved)
        if any(s in status for s in ["75 -", "80 -"]):
            continue

        channel_ids = (
            fields.get("Editor's Slack Channel", [])
            or fields.get("Slack ID Channel (from Assigned Editor)", [])
        )
        if not channel_ids:
            continue

        ch_id = channel_ids[0] if isinstance(channel_ids, list) else channel_ids
        channel_videos.setdefault(ch_id, []).append(v)

    discrepancies = []

    for ch_id, videos in channel_videos.items():
        # Read channel messages once per channel
        try:
            messages = read_slack_channel(ch_id, since_hours=hours, include_threads=False)
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

            # Resolve client name for matching
            client_ids = fields.get("Client", [])
            client_name = ""
            if client_ids and client_map:
                cid = client_ids[0] if isinstance(client_ids, list) else client_ids
                client_name = client_map.get(cid, "")

            for msg in messages:
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
                    continue

                for keyword in COMPLETION_KEYWORDS:
                    if keyword in text:
                        msg_time = msg.get("datetime", "")
                        discrepancies.append({
                            "video": display_name,
                            "editor": editor,
                            "airtable_status": status,
                            "slack_says": msg.get("text", "")[:120],
                            "when": msg_time,
                            "issue": f"Slack mentions '{keyword}' but Airtable is '{status}'",
                        })
                        break  # one match per message is enough

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

        # Only check videos currently with editors (not sent to client / approved)
        if any(s in status for s in ["75 -", "80 -"]):
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
            messages = read_slack_channel(ch_id, since_hours=hours, include_threads=False)
        except Exception:
            messages = []

        if not messages:
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

        # Only track Current/Onboarding clients
        if info["status"] not in ("Current", "Onboarding"):
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
        target_str = str(counts["deliverables_raw"]).lower()
        # Remove resolution numbers (720, 1080, 2160, 4k)
        cleaned = re.sub(r"\b(720|1080|2160|4k)\w*", "", target_str)
        nums = re.findall(r"\d+", cleaned)
        package = int(nums[0]) if nums else 0

        delivered = counts["delivered"]
        remaining = max(0, package - delivered) if package > 0 else 0

        results.append({
            "client": name,
            "package": f"{package}/mo" if package > 0 else "?",
            "delivered": delivered,
            "active": counts["active"],
            "remaining": remaining,
            "on_track": delivered >= package if package > 0 else None,
        })

    return results


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

    # Deliverables
    total_delivered = 0
    total_package = 0
    if "client_deliverables" in results:
        items = results["client_deliverables"]
        month = datetime.now().strftime("%b %Y")
        total_delivered = sum(d["delivered"] for d in items)
        total_package = sum(
            int(d["package"].split("/")[0])
            for d in items
            if d["package"] != "?"
        )

        lines.append(f"### Deliverables This Month ({month})")
        if items:
            lines.append("| Client | Package | Delivered | Active | Remaining |")
            lines.append("|--------|---------|-----------|--------|-----------|")
            for d in items:
                remaining = str(d["remaining"]) if d["remaining"] > 0 else "-"
                lines.append(
                    f"| {d['client']} | {d['package']} | {d['delivered']} "
                    f"| {d['active']} | {remaining} |"
                )
        else:
            lines.append("No active clients with deliverables data.")
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
    if total_package > 0:
        summary_parts.append(f"{total_delivered} of {total_package} monthly videos delivered")
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
        choices=["all", "status", "gaps", "deliverables"],
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

        if args.check in ("all", "deliverables"):
            print("Phase 2: Checking client deliverables...", file=sys.stderr)
            all_videos = get_all_videos()
            results["client_deliverables"] = check_client_deliverables(
                all_videos, client_info
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
