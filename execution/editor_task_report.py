#!/usr/bin/env python3
"""
Editor Task Report - Cross-references Slack activity with Airtable pipeline
Produces per-editor task summaries with Airtable status annotations

Usage:
    python execution/editor_task_report.py
    python execution/editor_task_report.py --editor megh
    python execution/editor_task_report.py --hours 24 --output json
    python execution/editor_task_report.py --editors-only
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Add execution dir to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from slack_read_channel import read_slack_channel
from airtable_read import read_airtable_records


# ============================================================================
# EDITOR CHANNEL REGISTRY
# ============================================================================

EDITOR_CHANNELS = {
    "rafael":   {"id": "C070VSRPP6H", "name": "rafael-editing"},
    "ananda":   {"id": "C071NUME7EC", "name": "ananda-editing"},
    "amna":     {"id": "C079U4HF8GM", "name": "amna-editing"},
    "megh":     {"id": "C08HNVDCGQ4", "name": "megh-editing"},
    "suhaib":   {"id": "C08PCKQBTV5", "name": "suhaib-editing"},
    "sakib":    {"id": "C09LQKUC7E0", "name": "sakib-editing"},
    "syed n":   {"id": "C09S6EXECQP", "name": "syed-n-editing"},
    "chris":    {"id": "C09S8G1LKT6", "name": "chris-editing"},
    "jov":      {"id": "C0A0SFWPR3L", "name": "jov-editing"},
    "sanjit":   {"id": "C0A13RZCLMT", "name": "sanjit-editing"},
    "raj":      {"id": "C0A17EL29EZ", "name": "raj-editing"},
    "lin":      {"id": "C0A1PCUQA7M", "name": "lin-editing"},
    "ruben":    {"id": "C0A2PK6FWF3", "name": "ruben-editing"},
    "sebastian":{"id": "C0A3CPG5Z3Q", "name": "seba-editing"},
    "golden":   {"id": "C0A3D58KYT1", "name": "golden-2-editing"},
    "kyrylo":   {"id": "C0A5H3PKA3E", "name": "kyrylo-editing"},
    "rafiu":    {"id": "C0A5HJGF7EX", "name": "rafiu-editing"},
    "shafen":   {"id": "C0A7UAZ22DN", "name": "shafen-editing"},
    "ghayas":   {"id": "C0A7Z3F8K8T", "name": "ghayas-editing"},
    "jaydi":    {"id": "C0ABFUHSWN9", "name": "jaydi-editing"},
    "alaa":     {"id": "C0ACDK8D248", "name": "alaa-editing"},
    "denis":    {"id": "C0ACR0N0R98", "name": "denis-editing"},
    "anuj":     {"id": "C0A73RECBQS", "name": "anuj-editing"},
}

# Status progression order (for priority logic)
STATUS_ORDER = {
    "41 - Sent to Editor": 41,
    "50 - Editor Confirmed": 50,
    "59 - Editing Revisions": 59,
    "60 - Submitted for QC": 60,
    "75 - Sent to Client For Review": 75,
    "80 - Approved By Client": 80,
    "100 - Scheduled - DONE": 100,
    "40 - Client Sent Raw Footage": 40,
    "Waiting For Input From Client": 35,
}

URGENT_KEYWORDS = ["urgent", "asap", "critical", "extremely urgent", "immediately", "right away"]
DONE_KEYWORDS = ["sent to the client for final review", "good job", "approved by client"]
BLOCKER_KEYWORDS = ["blocked", "waiting", "can't", "missing", "no asset", "doesn't have"]


# ============================================================================
# DATA FETCHING
# ============================================================================

def get_airtable_pipeline():
    """Fetch active videos grouped by editor, with resolved client/editor names."""
    print("  Fetching Airtable videos...", file=sys.stderr)

    # Pull active videos
    active_filter = (
        "OR("
        "{Editing Status}='40 - Client Sent Raw Footage',"
        "{Editing Status}='41 - Sent to Editor',"
        "{Editing Status}='50 - Editor Confirmed',"
        "{Editing Status}='59 - Editing Revisions',"
        "{Editing Status}='60 - Submitted for QC',"
        "{Editing Status}='75 - Sent to Client For Review',"
        "{Editing Status}='80 - Approved By Client'"
        ")"
    )
    videos = read_airtable_records(
        "Videos",
        filter_formula=active_filter,
        fields=["Video ID", "Client", "Video Number", "Format", "Editing Status", "Assigned Editor"]
    )

    print("  Fetching client names...", file=sys.stderr)
    clients_raw = read_airtable_records("Clients", fields=["Name"])
    client_map = {r["id"]: r["fields"].get("Name", "?") for r in clients_raw}

    print("  Fetching team members...", file=sys.stderr)
    team_raw = read_airtable_records("Team", fields=["Name"])
    editor_map = {r["id"]: r["fields"].get("Name", "?") for r in team_raw}

    # Group by editor
    pipeline = {}
    for record in videos:
        f = record["fields"]
        editor_ids = f.get("Assigned Editor", [])
        editor_name = editor_map.get(editor_ids[0], "Unassigned") if editor_ids else "Unassigned"
        editor_key = editor_name.lower()

        client_ids = f.get("Client", [])
        client_name = client_map.get(client_ids[0], "?") if client_ids else "?"

        video = {
            "video_id": f.get("Video ID"),
            "client": client_name,
            "video_number": f.get("Video Number", "?"),
            "format": f.get("Format", "?"),
            "status": f.get("Editing Status", "?"),
            "display_name": f"{client_name} #{f.get('Video Number', '?')}",
        }

        if editor_key not in pipeline:
            pipeline[editor_key] = []
        pipeline[editor_key].append(video)

    # Sort each editor's videos by status progression
    for editor_key in pipeline:
        pipeline[editor_key].sort(
            key=lambda v: (v["client"], STATUS_ORDER.get(v["status"], 0))
        )

    return pipeline


def get_slack_activity(channel_id, hours):
    """Read Slack messages from an editor channel with thread replies."""
    try:
        messages = read_slack_channel(
            channel=channel_id,
            since_hours=hours,
            include_threads=True,
            max_threads=50
        )
        return messages
    except Exception as e:
        print(f"    Warning: Could not read channel {channel_id}: {e}", file=sys.stderr)
        return []


# ============================================================================
# ANALYSIS (deterministic, no LLM)
# ============================================================================

def _match_video_to_messages(video, messages):
    """Find Slack messages that reference a specific video.

    Uses two strategies:
    1. Direct matching: message text contains client name + video number
    2. Proximity matching: messages within 5 minutes after an Airtable bot
       notification about this video are assumed to be about it.
       This handles cases like: Airtable says "Sam40 reviewed" then Samu says
       "the video is extremely urgent" without naming Sam40 again.
    """
    client = video["client"].lower()
    vid_num = str(video["video_number"]).lower().strip()
    matched = []
    matched_timestamps = set()

    # Build search patterns
    # e.g., "Nicolas37", "Nicolas 37", "Sam40", "Spree 2", "Fibbler6"
    patterns = []
    if client != "?" and vid_num != "?":
        patterns.append(re.compile(rf"\b{re.escape(client)}\s*{re.escape(vid_num)}\b", re.IGNORECASE))
        if len(vid_num) > 1:
            patterns.append(re.compile(rf"\b{re.escape(vid_num)}\b", re.IGNORECASE))

    combined_name = f"{client}{vid_num}".lower()

    # Pass 1: Direct matching
    airtable_bot_timestamps = []  # timestamps of Airtable bot msgs about this video
    for msg in messages:
        text = msg.get("text", "").lower()
        is_match = False

        if combined_name in text.replace(" ", ""):
            is_match = True
            # Track Airtable bot messages for proximity matching
            if msg.get("user", "").lower() == "airtable" or msg.get("username", "") == "airtable2":
                try:
                    airtable_bot_timestamps.append(float(msg.get("timestamp", 0)))
                except (ValueError, TypeError):
                    pass

        if not is_match:
            for pattern in patterns:
                if pattern.search(text):
                    is_match = True
                    break

        if is_match:
            matched.append(msg)
            matched_timestamps.add(msg.get("timestamp"))

        # Also check thread replies
        for reply in msg.get("thread_replies", []):
            reply_text = reply.get("text", "").lower()
            for pattern in patterns:
                if pattern.search(reply_text):
                    if msg.get("timestamp") not in matched_timestamps:
                        matched.append(msg)
                        matched_timestamps.add(msg.get("timestamp"))
                    break

    # Pass 2: Proximity matching
    # Messages within 5 minutes AFTER an Airtable bot notification about this
    # video are contextually about it (user taught us this rule).
    PROXIMITY_SECONDS = 300  # 5 minutes
    if airtable_bot_timestamps:
        for msg in messages:
            if msg.get("timestamp") in matched_timestamps:
                continue
            # Skip other Airtable bot messages
            if msg.get("user", "").lower() == "airtable" or msg.get("username", "") == "airtable2":
                continue
            # Skip check-in prompts
            if "Send your *check in*" in msg.get("text", ""):
                continue
            try:
                msg_ts = float(msg.get("timestamp", 0))
            except (ValueError, TypeError):
                continue
            for bot_ts in airtable_bot_timestamps:
                # Message posted within 5 min AFTER the bot notification
                if 0 < (msg_ts - bot_ts) <= PROXIMITY_SECONDS:
                    matched.append(msg)
                    matched_timestamps.add(msg.get("timestamp"))
                    break

    return matched


def _classify_priority(video, matched_messages):
    """Classify task priority based on Airtable status and Slack context."""
    status = video["status"]
    all_text = " ".join(m.get("text", "") for m in matched_messages).lower()

    # Include thread reply text too
    for msg in matched_messages:
        for reply in msg.get("thread_replies", []):
            all_text += " " + reply.get("text", "").lower()

    # DONE: approved by client (Airtable status is source of truth)
    if status == "80 - Approved By Client":
        return "DONE"
    # Only mark DONE from Slack keywords if Airtable status also confirms
    # it's past active editing (75+ means with client or approved)
    if STATUS_ORDER.get(status, 0) >= 75:
        for kw in DONE_KEYWORDS:
            if kw in all_text:
                return "DONE"

    # HIGH: urgent keywords or revision warnings
    for kw in URGENT_KEYWORDS:
        if kw in all_text:
            return "HIGH"
    if "find another editor" in all_text or "can't have this many revisions" in all_text:
        return "HIGH"
    if status == "59 - Editing Revisions":
        return "HIGH"
    if status == "60 - Submitted for QC":
        return "HIGH"

    # MEDIUM: actively being worked on
    if status in ("50 - Editor Confirmed", "41 - Sent to Editor", "75 - Sent to Client For Review"):
        return "MEDIUM"

    return "MEDIUM"


def _extract_context(matched_messages):
    """Extract key context snippets from matched Slack messages."""
    context_lines = []

    for msg in matched_messages:
        user = msg.get("user", "Unknown")
        text = msg.get("text", "").strip()
        dt = msg.get("datetime", "")

        # Skip empty or very short messages
        if len(text) < 3:
            continue

        # Skip automated check-in prompts
        if "Send your *check in*" in text:
            continue

        # Condense Airtable bot notifications to one line
        is_airtable = user.lower() == "airtable" or msg.get("username", "") == "airtable2"
        if is_airtable:
            # Extract the key action from Airtable bots
            if "ready for review" in text.lower():
                display_text = "[Airtable] Submitted for review"
            elif "revisions that need to be implemented" in text.lower():
                display_text = "[Airtable] Revisions requested"
            elif "sent to the client for final review" in text.lower():
                display_text = "[Airtable] Sent to client - approved"
            elif "new video was assigned" in text.lower():
                display_text = "[Airtable] New video assigned"
            elif "Editor Confirmed" in text:
                display_text = "[Airtable] Editor confirmed assignment"
            else:
                display_text = "[Airtable] " + text[:80]
            context_lines.append(f"[{dt}] {display_text}")
            continue

        # Clean up Slack formatting for human messages
        display_text = text[:200] + "..." if len(text) > 200 else text
        display_text = re.sub(r"<@[A-Z0-9]+>", "@user", display_text)
        display_text = re.sub(r"<(https?://[^|>]+)\|?[^>]*>", r"\1", display_text)
        # Collapse newlines
        display_text = re.sub(r"\n+", " | ", display_text).strip()

        context_lines.append(f"[{dt}] {user}: {display_text}")

        # Include thread replies
        for reply in msg.get("thread_replies", []):
            r_user = reply.get("user", "Unknown")
            r_text = reply.get("text", "").strip()
            r_dt = reply.get("datetime", "")
            if len(r_text) >= 3:
                r_text = r_text[:200] + "..." if len(r_text) > 200 else r_text
                r_text = re.sub(r"<@[A-Z0-9]+>", "@user", r_text)
                r_text = re.sub(r"\n+", " | ", r_text).strip()
                context_lines.append(f"  -> [{r_dt}] {r_user}: {r_text}")

    return context_lines


def _generate_bottom_line(editor_name, tasks, airtable_videos, has_slack_activity):
    """Generate a one-line summary for the editor."""
    if not has_slack_activity and not airtable_videos:
        return "No active videos, no messages. May be new/inactive editor."

    if not has_slack_activity and airtable_videos:
        count = len(airtable_videos)
        return f"No check-ins or updates in this period. {count} active video(s) need follow-up."

    high_tasks = [t for t in tasks if t["priority"] == "HIGH"]
    done_tasks = [t for t in tasks if t["priority"] == "DONE"]

    parts = []
    if high_tasks:
        names = ", ".join(t["display_name"] for t in high_tasks[:3])
        parts.append(f"Priority: {names}")
    if done_tasks:
        parts.append(f"{len(done_tasks)} video(s) approved/complete")

    remaining = len(airtable_videos) - len(done_tasks)
    if remaining > 0:
        parts.append(f"{remaining} active in pipeline")

    return ". ".join(parts) + "." if parts else "On track."


def analyze_editor(editor_key, slack_messages, airtable_videos):
    """Analyze a single editor's status by cross-referencing Slack and Airtable."""
    channel_info = EDITOR_CHANNELS.get(editor_key, {})
    editor_display = editor_key.title()
    channel_name = channel_info.get("name", f"{editor_key}-editing")

    has_slack = bool(slack_messages)
    # Filter out automated check-in bot messages for activity detection
    human_messages = [
        m for m in slack_messages
        if "Send your *check in*" not in m.get("text", "")
    ]
    has_human_slack = bool(human_messages)

    tasks = []

    # Build tasks from Airtable videos
    for video in (airtable_videos or []):
        matched = _match_video_to_messages(video, slack_messages)
        priority = _classify_priority(video, matched)
        context = _extract_context(matched)

        tasks.append({
            "display_name": video["display_name"],
            "client": video["client"],
            "video_number": video["video_number"],
            "airtable_status": video["status"],
            "priority": priority,
            "context": context,
            "matched_message_count": len(matched),
        })

    # Check for unmatched Slack activity (tasks not in Airtable)
    matched_msg_timestamps = set()
    for video in (airtable_videos or []):
        for msg in _match_video_to_messages(video, slack_messages):
            matched_msg_timestamps.add(msg.get("timestamp"))

    unmatched_important = []
    for msg in human_messages:
        if msg.get("timestamp") not in matched_msg_timestamps:
            text = msg.get("text", "").strip()
            # Only flag substantive unmatched messages
            if len(text) > 30 and not text.startswith("Hey <@"):
                unmatched_important.append(msg)

    # Sort tasks: HIGH first, then MEDIUM, then DONE, then LOW
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "DONE": 3}
    tasks.sort(key=lambda t: priority_order.get(t["priority"], 2))

    bottom_line = _generate_bottom_line(editor_display, tasks, airtable_videos, has_human_slack)

    # Detect flags
    flags = []
    if any(t["priority"] == "HIGH" for t in tasks):
        high_names = [t["display_name"] for t in tasks if t["priority"] == "HIGH"]
        flags.append(("Urgent/Escalated", ", ".join(high_names[:3])))
    if not has_human_slack and airtable_videos:
        flags.append(("No Activity", "No check-ins, needs follow-up"))

    approved = [t for t in tasks if t["airtable_status"] == "80 - Approved By Client"]
    if approved:
        names = ", ".join(t["display_name"] for t in approved)
        flags.append(("Approved by Client", names))

    return {
        "editor_key": editor_key,
        "editor_display": editor_display,
        "channel_name": channel_name,
        "airtable_videos": airtable_videos or [],
        "tasks": tasks,
        "bottom_line": bottom_line,
        "flags": flags,
        "has_activity": has_human_slack,
        "slack_message_count": len(slack_messages),
        "unmatched_messages": len(unmatched_important),
    }


# ============================================================================
# REPORT FORMATTING
# ============================================================================

def format_markdown_report(all_editors, hours):
    """Format the full report as markdown text."""
    lines = []
    lines.append("## Editor Task Report ({}h Slack + Airtable Cross-Reference)".format(hours))
    lines.append("Generated: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M")))
    lines.append("")
    lines.append("---")

    all_flags = {"Urgent/Escalated": [], "Approved by Client": [],
                 "No Activity": [], "Heavy Backlog": []}

    for editor_data in all_editors:
        lines.append("")
        lines.append("### #{} ({})".format(
            editor_data["channel_name"], editor_data["editor_display"]
        ))
        lines.append("")

        # Airtable pipeline table
        videos = editor_data["airtable_videos"]
        if videos:
            lines.append("**Airtable Pipeline:** {} active video{}".format(
                len(videos), "s" if len(videos) != 1 else ""
            ))
            lines.append("| Video | Airtable Status |")
            lines.append("|-------|--------|")
            for v in videos:
                lines.append("| {} | {} |".format(v["display_name"], v["status"]))
            lines.append("")

            if len(videos) >= 6:
                all_flags["Heavy Backlog"].append(
                    "{} ({} videos)".format(editor_data["editor_display"], len(videos))
                )
        else:
            lines.append("**Airtable Pipeline:** 0 active videos")
            lines.append("")

        # Tasks
        tasks = editor_data["tasks"]
        if tasks:
            for i, task in enumerate(tasks, 1):
                lines.append("**{}. {} - {}** `{}`".format(
                    i, task["display_name"],
                    _task_description(task),
                    task["priority"]
                ))
                # Context from Slack
                for ctx in task["context"][:5]:  # Max 5 context lines per task
                    lines.append("- {}".format(ctx))
                lines.append("- **Airtable:** {}".format(task["airtable_status"]))
                lines.append("")
        elif not editor_data["has_activity"]:
            lines.append("**No Slack activity in {}h.** Only automated check-in prompts.".format(hours))
            lines.append("")

        # Bottom line
        lines.append("**Bottom line:** {}".format(editor_data["bottom_line"]))
        lines.append("")
        lines.append("---")

        # Collect flags
        for flag_type, flag_detail in editor_data["flags"]:
            if flag_type in all_flags:
                all_flags[flag_type].append(
                    "{} ({})".format(editor_data["editor_display"], flag_detail)
                )

    # Summary flags table
    lines.append("")
    lines.append("## Summary Flags")
    lines.append("")
    lines.append("| Category | Editors |")
    lines.append("|----------|---------|")
    for category, editors in all_flags.items():
        if editors:
            lines.append("| **{}** | {} |".format(category, "; ".join(editors)))
    lines.append("")

    return "\n".join(lines)


def _task_description(task):
    """Generate a short task description from status and context."""
    status = task["airtable_status"]
    context_text = " ".join(task["context"]).lower()

    if status == "80 - Approved By Client":
        return "Approved by Client"
    elif status == "75 - Sent to Client For Review":
        return "With Client for Review"
    elif status == "60 - Submitted for QC":
        return "Submitted for QC"
    elif status == "59 - Editing Revisions":
        if "urgent" in context_text or "asap" in context_text:
            return "Urgent Revisions"
        return "Revisions Needed"
    elif status == "50 - Editor Confirmed":
        return "In Progress"
    elif status == "41 - Sent to Editor":
        return "Assigned, Awaiting Start"
    elif status == "40 - Client Sent Raw Footage":
        return "Footage Received"
    else:
        return status


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Editor Task Report - Slack + Airtable cross-reference",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              Full report, all editors
  %(prog)s --editor megh                Single editor
  %(prog)s --hours 24 --output json     JSON output, last 24h
  %(prog)s --editors-only               Skip editors with no active videos
        """
    )
    parser.add_argument("--hours", type=int, default=48,
                        help="Hours to look back for Slack activity (default: 48)")
    parser.add_argument("--editor", type=str, default=None,
                        help="Run for a specific editor only (e.g., 'megh')")
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown",
                        help="Output format (default: markdown)")
    parser.add_argument("--editors-only", action="store_true", default=False,
                        help="Only show editors with active Airtable videos")

    args = parser.parse_args()

    try:
        # Phase 1: Fetch Airtable pipeline
        print("Phase 1: Fetching Airtable pipeline...", file=sys.stderr)
        pipeline = get_airtable_pipeline()
        total_videos = sum(len(v) for v in pipeline.values())
        print(f"  Found {total_videos} active videos across {len(pipeline)} editors", file=sys.stderr)

        # Determine which editors to process
        if args.editor:
            editor_key = args.editor.lower()
            if editor_key not in EDITOR_CHANNELS:
                print(f"Error: Unknown editor '{args.editor}'. Available: {', '.join(sorted(EDITOR_CHANNELS.keys()))}", file=sys.stderr)
                return 1
            editors_to_process = {editor_key: EDITOR_CHANNELS[editor_key]}
        else:
            editors_to_process = EDITOR_CHANNELS

        # Phase 2: Read Slack channels and analyze
        print(f"\nPhase 2: Reading {len(editors_to_process)} editor channel(s)...", file=sys.stderr)
        all_editors = []

        for editor_key, channel_info in sorted(editors_to_process.items()):
            airtable_videos = pipeline.get(editor_key, [])

            # Skip editors with no active videos if --editors-only
            if args.editors_only and not airtable_videos:
                continue

            print(f"  Reading #{channel_info['name']}...", file=sys.stderr)
            slack_messages = get_slack_activity(channel_info["id"], args.hours)
            print(f"    {len(slack_messages)} messages, {len(airtable_videos)} Airtable videos", file=sys.stderr)

            # Analyze
            editor_data = analyze_editor(editor_key, slack_messages, airtable_videos)
            all_editors.append(editor_data)

        # Phase 3: Output
        print(f"\nPhase 3: Generating report...", file=sys.stderr)

        if args.output == "json":
            # Strip non-serializable stuff and output
            output = {
                "generated": datetime.now().isoformat(),
                "hours_scanned": args.hours,
                "editors": all_editors,
            }
            print(json.dumps(output, indent=2, default=str))
        else:
            report = format_markdown_report(all_editors, args.hours)
            print(report)

        print(f"\nDone. {len(all_editors)} editors processed.", file=sys.stderr)
        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
