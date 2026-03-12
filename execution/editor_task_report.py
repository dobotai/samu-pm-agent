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
from datetime import datetime, timedelta, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

# Add execution dir to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from slack_read_channel import read_slack_channel
from airtable_read import read_airtable_records
from slack_list_channels import list_slack_channels
from constants import (
    STATUS_ORDER, QC_STATUSES, INACTIVE_CLIENT_STATUSES,
    EDITOR_ACTIVE_STATUSES, POST_DEADLINE_STATUSES,
    EDITOR_NUDGE_HOURS, EDITOR_WHATSAPP_HOURS,
    HEAVY_LOAD_THRESHOLD, REVISION_LOOP_THRESHOLD,
    STALE_QC_HOURS, STALE_APPROVAL_DAYS,
    SIMON_SLACK_USER_ID, OPS_MANAGER_IDS,
    THUMBNAIL_NEEDS_WORK, THUMBNAIL_IN_PROGRESS,
    THUMBNAIL_IN_REVISION, THUMBNAIL_APPROVED,
    THUMBNAIL_ACTIVE_STATUSES, RAM_CHANNEL_ID,
)


# ============================================================================
# EDITOR CHANNEL REGISTRY
# ============================================================================

# Editor channels are discovered dynamically from Slack via discover_editor_channels().
# This dict is populated once at script startup and then used as a module-level lookup.
EDITOR_CHANNELS = {}


def discover_editor_channels():
    """Discover *-editing Slack channels and cross-reference with Airtable Team table.

    Returns a dict keyed by editor name (lowercase, matching Airtable):
        {"sakib": {"id": "C09LQKUC7E0", "name": "sakib-editing"}, ...}

    Channel-to-editor matching:
    1. Fetch all *-editing channels from Slack
    2. Fetch Team table from Airtable to get canonical editor names
    3. Match channels to editors by checking if the editor's first name appears
       in the channel name (handles mismatches like seba-editing -> Sebastian)
    4. Any channel that doesn't match a team member is keyed by channel name
       (e.g. "golden-2-editing" -> "golden 2" if no Team match)
    """
    print("  Discovering editor channels from Slack...", file=sys.stderr)
    channels = list_slack_channels(filter_pattern="-editing")
    channels = [ch for ch in channels if not ch.get("is_archived", False)]
    print(f"  Found {len(channels)} active *-editing channels", file=sys.stderr)

    # Get canonical editor names from Airtable Team table
    team_raw = read_airtable_records("Team", fields=["Name"])
    team_names = [r["fields"].get("Name", "") for r in team_raw if r["fields"].get("Name")]

    # Build a first-name lookup: {"sebastian": "Sebastian", "sakib": "Sakib", ...}
    first_name_lookup = {}
    for name in team_names:
        first = name.strip().split()[0].lower()
        first_name_lookup[first] = name

    result = {}
    for ch in channels:
        ch_name = ch["name"]  # e.g. "seba-editing", "golden-2-editing"
        stem = ch_name.replace("-editing", "")  # e.g. "seba", "golden-2"

        # Try to match against Airtable team members
        matched_name = None

        # Direct match: stem == first name (covers most cases)
        if stem in first_name_lookup:
            matched_name = first_name_lookup[stem]
        else:
            # Partial match: check if any team first name starts with stem or vice versa
            # Handles seba -> sebastian, syed-n -> syed n, etc.
            stem_normalized = stem.replace("-", " ")
            for first, full_name in first_name_lookup.items():
                if first.startswith(stem_normalized.split()[0]) and len(stem_normalized.split()[0]) >= 3:
                    matched_name = full_name
                    break
                if stem_normalized.startswith(first) and len(first) >= 3:
                    matched_name = full_name
                    break

        editor_key = matched_name.lower() if matched_name else stem.replace("-", " ")
        result[editor_key] = {"id": ch["id"], "name": ch_name}

    return result

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
        "{Editing Status}='60 - Internal Review',"
        "{Editing Status}='75 - Sent to Client For Review',"
        "{Editing Status}='80 - Approved By Client'"
        ")"
    )
    videos = read_airtable_records(
        "Videos",
        filter_formula=active_filter,
        fields=["Video ID", "Client", "Video Number", "Format", "Editing Status", "Assigned Editor", "Deadline", "Last Modified (Editing Status)", "Thumbnail Status", "Thumbnail Deadline"]
    )

    print("  Fetching client names...", file=sys.stderr)
    clients_raw = read_airtable_records("Clients", fields=["Name", "Status"])
    client_map = {r["id"]: r["fields"].get("Name", "?") for r in clients_raw}
    inactive_clients = {
        r["fields"].get("Name", "").lower()
        for r in clients_raw
        if r["fields"].get("Status", "") in INACTIVE_CLIENT_STATUSES
    }

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

        # Skip videos belonging to inactive/paused/churned clients
        if client_name.lower() in inactive_clients:
            continue

        video = {
            "video_id": f.get("Video ID"),
            "client": client_name,
            "video_number": f.get("Video Number", "?"),
            "format": f.get("Format", "?"),
            "status": f.get("Editing Status", "?"),
            "display_name": f"{client_name} #{f.get('Video Number', '?')}",
            "deadline": f.get("Deadline"),
            "last_modified": f.get("Last Modified (Editing Status)"),
            "thumbnail_status": f.get("Thumbnail Status", ""),
            "thumbnail_deadline": f.get("Thumbnail Deadline"),
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
            # Require context prefix to avoid matching times/quantities
            # e.g. "video 37", "#37", "vid37" but not "10am" or "sent 10"
            patterns.append(re.compile(
                rf"(?:video\s*|vid\s*|#){re.escape(vid_num)}\b", re.IGNORECASE
            ))

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
    if status in QC_STATUSES:
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


def _detect_blockers(matched_messages):
    """Check matched messages for blocker keywords.

    Scans editor (non-bot, non-Simon) messages for BLOCKER_KEYWORDS.
    Returns list of {"keyword": str, "text": str, "user": str}
    """
    blockers = []
    for msg in matched_messages:
        user = msg.get("user", "")
        user_id = msg.get("user_id", "")
        # Only check editor messages (skip bots and Simon)
        if user.lower() == "airtable" or msg.get("username", "") == "airtable2":
            continue
        if user_id in OPS_MANAGER_IDS:
            continue
        text = msg.get("text", "")
        if not text or len(text) < 5:
            continue
        text_lower = text.lower()
        for kw in BLOCKER_KEYWORDS:
            if kw in text_lower:
                blockers.append({
                    "keyword": kw,
                    "text": text[:100],
                    "user": user,
                })
                break  # one keyword per message
    return blockers


def _status_age(last_modified_str):
    """Days since status last changed. Returns 'Xd' or '' if unknown."""
    if not last_modified_str:
        return ""
    try:
        dt = datetime.fromisoformat(last_modified_str.replace("Z", "+00:00"))
        days = (datetime.now(dt.tzinfo) - dt).days
        return f"{days}d"
    except (ValueError, TypeError):
        return ""


def _parse_deadline(deadline_str):
    """Parse Airtable deadline string to date. Returns None if invalid/empty."""
    if not deadline_str:
        return None
    try:
        return datetime.strptime(deadline_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _days_until_deadline(deadline_str):
    """Return days until deadline (negative = overdue). None if no deadline."""
    d = _parse_deadline(deadline_str)
    if d is None:
        return None
    return (d - date.today()).days


def _deadline_display(deadline_str, status=""):
    """Format deadline for compact table display.

    Appends '⚠ refresh' when deadline is past but status indicates active work
    (59/60/75) — these deadlines are likely stale since Simon updates weekly.
    """
    days = _days_until_deadline(deadline_str)
    if days is None:
        return ""
    # Statuses where an overdue deadline is normal (active revision/QC/client cycle)
    active_cycle_statuses = {"59 - Editing Revisions", "75 - Sent to Client For Review"}
    active_cycle_statuses.update(QC_STATUSES)
    if days < 0:
        label = f"{abs(days)}d overdue"
        if status in active_cycle_statuses:
            label += " (check deadline)" if abs(days) >= 7 else " (stale?)"
        return label
    elif days == 0:
        return "due today"
    elif days == 1:
        return "due tomorrow"
    else:
        d = _parse_deadline(deadline_str)
        return d.strftime("%b %d")


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

    # Calculate hours since last human message (for escalation timing)
    hours_since_last = None
    last_message_text = None
    if human_messages:
        try:
            latest_msg = max(human_messages, key=lambda m: float(m.get("timestamp", 0)))
            last_ts = float(latest_msg.get("timestamp", 0))
            hours_since_last = (datetime.now() - datetime.fromtimestamp(last_ts)).total_seconds() / 3600
            hours_since_last = round(hours_since_last, 1)
            raw = latest_msg.get("text", "").strip()
            raw = re.sub(r"<@[A-Z0-9]+>", "@user", raw)
            raw = re.sub(r"\n+", " | ", raw)
            last_message_text = raw[:120] if raw else None
        except (ValueError, TypeError):
            pass

    # Detect ops manager unanswered questions (Simon + Jonathan)
    simon_unanswered = None
    simon_msgs = [
        m for m in slack_messages
        if m.get("user_id") in OPS_MANAGER_IDS
        and len(m.get("text", "")) > 5
        and "Send your *check in*" not in m.get("text", "")
        and "archived the channel" not in m.get("text", "")
        and "joined the channel" not in m.get("text", "")
        and m.get("subtype", "") not in ("channel_archive", "channel_join", "channel_leave")
    ]
    if simon_msgs:
        # Find the latest ops manager message
        latest_simon = max(simon_msgs, key=lambda m: float(m.get("timestamp", 0)))
        simon_ts = float(latest_simon.get("timestamp", 0))
        # Check if any non-ops, non-bot message came after (including thread replies)
        def _is_valid_reply(m):
            return (
                float(m.get("timestamp", 0)) > simon_ts
                and m.get("user_id") not in OPS_MANAGER_IDS
                and m.get("user", "").lower() != "airtable"
                and m.get("username", "") != "airtable2"
                and "Send your *check in*" not in m.get("text", "")
            )

        has_reply = any(_is_valid_reply(m) for m in slack_messages)
        # Also check thread replies (editor might reply in a thread)
        if not has_reply:
            for m in slack_messages:
                for reply in m.get("thread_replies", []):
                    if _is_valid_reply(reply):
                        has_reply = True
                        break
                if has_reply:
                    break
        if not has_reply:
            hours_ago = (datetime.now() - datetime.fromtimestamp(simon_ts)).total_seconds() / 3600
            simon_unanswered = {
                "text": latest_simon.get("text", "")[:60],
                "hours_ago": round(hours_ago, 1),
            }

    tasks = []

    # Build tasks from Airtable videos
    for video in (airtable_videos or []):
        matched = _match_video_to_messages(video, slack_messages)
        priority = _classify_priority(video, matched)
        context = _extract_context(matched)
        blockers = _detect_blockers(matched)

        tasks.append({
            "display_name": video["display_name"],
            "client": video["client"],
            "video_number": video["video_number"],
            "airtable_status": video["status"],
            "deadline": video.get("deadline"),
            "last_modified": video.get("last_modified"),
            "thumbnail_status": video.get("thumbnail_status", ""),
            "thumbnail_deadline": video.get("thumbnail_deadline"),
            "priority": priority,
            "context": context,
            "matched_message_count": len(matched),
            "blockers": blockers,
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
        "hours_since_last_message": hours_since_last,
        "last_message_text": last_message_text,
        "simon_unanswered": simon_unanswered,
    }


# ============================================================================
# ACTIVE ALERTS DETECTION
# ============================================================================

def _detect_active_alerts(all_editors, all_tasks):
    """Detect cross-cutting alert patterns across editors and videos.

    Returns list of {"alert": str, "detail": str} dicts.
    """
    alerts = []

    # --- Revision loops ---
    # Count bot messages "[Airtable] Revisions requested" and
    # "[Airtable] Submitted for review" in context. A cycle = one of each.
    for task in all_tasks:
        context_text = " ".join(task.get("context", []))
        rev_count = context_text.count("[Airtable] Revisions requested")
        qc_count = context_text.count("[Airtable] Submitted for review")
        cycles = min(rev_count, qc_count)
        if cycles >= REVISION_LOOP_THRESHOLD:
            alerts.append({
                "alert": "Revision loop",
                "detail": f"{task['display_name']} ({task['editor']}) — "
                          f"{cycles} revision rounds in scan window",
            })

    # --- Heavy editor load ---
    for ed in all_editors:
        video_count = len(ed["airtable_videos"])
        if video_count >= HEAVY_LOAD_THRESHOLD:
            overdue = sum(
                1 for v in ed["airtable_videos"]
                if _days_until_deadline(v.get("deadline")) is not None
                and _days_until_deadline(v.get("deadline")) < 0
            )
            detail = f"{ed['editor_display']} — {video_count} videos"
            if overdue:
                detail += f", {overdue} overdue"
            alerts.append({"alert": "Heavy load", "detail": detail})

    # --- Simon unanswered ---
    for ed in all_editors:
        su = ed.get("simon_unanswered")
        if su:
            preview = su["text"].replace("\n", " ").strip()
            alerts.append({
                "alert": "Simon unanswered",
                "detail": f"{ed['editor_display']} — \"{preview}\" "
                          f"({su['hours_ago']:.0f}h ago, no reply)",
            })

    # --- Silent + approaching deadline ---
    for ed in all_editors:
        if ed["has_activity"]:
            continue
        approaching = [
            v for v in ed["airtable_videos"]
            if _days_until_deadline(v.get("deadline")) is not None
            and 0 <= _days_until_deadline(v.get("deadline")) <= 2
        ]
        if approaching:
            names = ", ".join(v["display_name"] for v in approaching[:3])
            alerts.append({
                "alert": "Silent + deadline",
                "detail": f"{ed['editor_display']} not responding, "
                          f"due soon: {names}",
            })

    # --- Stale QC (status 60, Last Modified 8h+ ago) ---
    for task in all_tasks:
        if task["airtable_status"] not in QC_STATUSES:
            continue
        lm = task.get("last_modified")
        if not lm:
            continue
        try:
            modified_dt = datetime.fromisoformat(lm.replace("Z", "+00:00"))
            hours_ago = (datetime.now(modified_dt.tzinfo) - modified_dt).total_seconds() / 3600
            if hours_ago >= STALE_QC_HOURS:
                alerts.append({
                    "alert": "Stale QC",
                    "detail": f"{task['display_name']} ({task['editor']}) "
                              f"submitted {int(hours_ago)}h ago",
                })
        except (ValueError, TypeError):
            pass

    # --- Stale approval (status 80, Last Modified 5+ days) ---
    for task in all_tasks:
        if task["airtable_status"] != "80 - Approved By Client":
            continue
        lm = task.get("last_modified")
        if not lm:
            continue
        try:
            modified_dt = datetime.fromisoformat(lm.replace("Z", "+00:00"))
            days_ago = (datetime.now(modified_dt.tzinfo) - modified_dt).days
            if days_ago >= STALE_APPROVAL_DAYS:
                alerts.append({
                    "alert": "Stale approval",
                    "detail": f"{task['display_name']} ({task['editor']}) "
                              f"approved {days_ago}d ago, not yet scheduled",
                })
        except (ValueError, TypeError):
            pass

    # --- Blocked videos ---
    for task in all_tasks:
        if task.get("blockers"):
            b = task["blockers"][0]  # First blocker per video
            alerts.append({
                "alert": "Blocked",
                "detail": f"{task['display_name']} ({task['editor']}) "
                          f"-- \"{b['text'][:60]}\"",
            })

    return alerts


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
                lines.append("| {} | {} |".format(
                    v["display_name"], v["status"]
                ))
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


def _get_latest_context_line(task):
    """Get the most recent meaningful Slack context line for a task (truncated)."""
    for ctx in task.get("context", []):
        # Skip Airtable bot lines — prefer human context
        if "[Airtable]" not in ctx:
            # Strip the timestamp prefix for compact display
            text = ctx
            if "] " in text:
                text = text.split("] ", 1)[-1]
            return text[:100] + "..." if len(text) > 100 else text
    # Fall back to most recent Airtable event
    for ctx in task.get("context", []):
        text = ctx
        if "] " in text:
            text = text.split("] ", 1)[-1]
        return text[:100] + "..." if len(text) > 100 else text
    return ""


# ---------------------------------------------------------------------------
# Bench & Thumbnail analysis
# ---------------------------------------------------------------------------

def detect_bench_editors(pipeline, all_editors):
    """Identify editors with 0 active videos who are available for assignment.

    Uses EDITOR_CHANNELS (discovered dynamically from Slack) as the canonical
    editor list. Any editor with a *-editing channel but 0 videos in the
    pipeline is on the bench.

    Returns: [{"editor": "Alaa", "note": "Last active 2d ago"}, ...]
    """
    active_editor_keys = set(pipeline.keys())
    # Build lookup for analyzed editor data
    ed_lookup = {ed["editor_key"]: ed for ed in all_editors}

    bench = []
    for editor_key in EDITOR_CHANNELS:
        if editor_key in active_editor_keys:
            continue

        ed_data = ed_lookup.get(editor_key)
        note = ""
        if ed_data:
            h = ed_data.get("hours_since_last_message")
            last_msg = ed_data.get("last_message_text", "")
            if h is not None:
                if h < 24:
                    time_part = "{}h ago".format(int(h))
                else:
                    time_part = "{}d ago".format(int(h / 24))
                if last_msg:
                    note = '"{}" ({})'.format(last_msg[:80], time_part)
                else:
                    note = "Last active {}".format(time_part)
            elif not ed_data.get("has_activity"):
                note = "No recent activity"
        else:
            note = "Channel not scanned"

        bench.append({"editor": editor_key.title(), "note": note})

    bench.sort(key=lambda e: e["editor"])
    return bench


def analyze_thumbnail_pipeline(all_tasks):
    """Categorize active videos by thumbnail status.

    Returns dict: new, in_revision, pending_feedback, total_queue, ram_slack_context
    """
    new = []
    in_revision = []
    pending_feedback = []

    in_progress = []

    for task in all_tasks:
        ts = (task.get("thumbnail_status") or "").strip()
        status = task.get("airtable_status", "")
        # Skip approved/done and raw footage (no thumbnail needed yet)
        if status in ("80 - Approved By Client", "100 - Scheduled - DONE",
                       "40 - Client Sent Raw Footage"):
            continue
        if ts == THUMBNAIL_NEEDS_WORK:
            new.append(task)
        elif ts == THUMBNAIL_IN_REVISION:
            in_revision.append(task)
        elif ts == THUMBNAIL_IN_PROGRESS:
            in_progress.append(task)

    return {
        "new": sorted(new, key=lambda t: t["display_name"]),
        "in_progress": sorted(in_progress, key=lambda t: t["display_name"]),
        "in_revision": sorted(in_revision, key=lambda t: t["display_name"]),
        "total_queue": len(new) + len(in_revision) + len(in_progress),
    }


def _get_ram_slack_context(hours):
    """Try to read Ram's thumbnail channel for recent activity context.

    Returns list of summary lines, or empty list if channel not found.
    """
    try:
        messages = read_slack_channel(RAM_CHANNEL_ID, limit=100, since_hours=hours,
                                       include_threads=False)
        if not messages:
            return ["No messages in thumbnail channel ({}h)".format(hours)]

        # Filter to human messages only
        human_msgs = [
            m for m in messages
            if "Send your *check in*" not in m.get("text", "")
            and m.get("user", "").lower() != "airtable"
            and m.get("username", "") != "airtable2"
            and len(m.get("text", "")) > 5
        ]

        context = []
        context.append("{} messages in thumbnail channel ({}h)".format(len(human_msgs), hours))

        if human_msgs:
            recent = sorted(human_msgs,
                            key=lambda m: float(m.get("timestamp", 0)),
                            reverse=True)[:3]
            for msg in recent:
                user = msg.get("user", "Unknown")
                text = msg.get("text", "").strip()[:120]
                text = re.sub(r"<@[A-Z0-9]+>", "@user", text)
                text = re.sub(r"\n+", " | ", text)
                ts = float(msg.get("timestamp", 0))
                h_ago = (datetime.now() - datetime.fromtimestamp(ts)).total_seconds() / 3600
                if h_ago < 24:
                    time_str = "{}h ago".format(int(h_ago))
                else:
                    time_str = "{}d ago".format(int(h_ago / 24))
                context.append("[{}] {}: {}".format(time_str, user, text))

        return context
    except Exception as e:
        print("  Warning: Could not read Ram's channel: {}".format(e), file=sys.stderr)
        return []


def _build_tasks_and_silent(all_editors):
    """Extract flat task list and silent editor list from analyzed editor data."""
    all_tasks = []
    silent_editors = []
    for ed in all_editors:
        editor_name = ed["editor_display"]
        for task in ed["tasks"]:
            task_copy = dict(task)
            task_copy["editor"] = editor_name
            all_tasks.append(task_copy)
        if not ed["has_activity"] and ed["airtable_videos"]:
            silent_editors.append({
                "editor": editor_name,
                "active_videos": len(ed["airtable_videos"]),
                "hours_since_last": ed.get("hours_since_last_message"),
            })
    return all_tasks, silent_editors


def _format_bench_section(bench_editors):
    """Format the BENCH section lines."""
    if not bench_editors:
        return []
    lines = []
    lines.append("### BENCH -- Available for Assignments ({})".format(len(bench_editors)))
    lines.append("| Editor | Notes |")
    lines.append("|--------|-------|")
    for e in bench_editors:
        lines.append("| {} | {} |".format(e["editor"], e["note"]))
    lines.append("")
    return lines


def _format_ram_section(thumb_data):
    """Format the RAM thumbnail pipeline section lines."""
    if not thumb_data:
        return []
    if not (thumb_data["new"] or thumb_data["in_progress"] or thumb_data["in_revision"]):
        return []
    lines = []
    queue = thumb_data["total_queue"]
    lines.append("### RAM -- Thumbnail Pipeline ({} in queue)".format(queue))

    if thumb_data["new"]:
        lines.append("")
        lines.append("**Needs Thumbnail ({}):**".format(len(thumb_data["new"])))
        lines.append("| # | Video | Editor | Thumb Deadline |")
        lines.append("|---|-------|--------|----------------|")
        for i, t in enumerate(thumb_data["new"], 1):
            td = t.get("thumbnail_deadline") or ""
            if td:
                td_date = _parse_deadline(td)
                if td_date:
                    days = (td_date - date.today()).days
                    if days < 0:
                        td = "{}d overdue".format(abs(days))
                    elif days == 0:
                        td = "today"
                    else:
                        td = td_date.strftime("%b %d")
            lines.append("| {} | {} | {} | {} |".format(
                i, t["display_name"], t.get("editor", ""), td))

    if thumb_data["in_progress"]:
        lines.append("")
        lines.append("**Ram Working On ({}):**".format(len(thumb_data["in_progress"])))
        for t in thumb_data["in_progress"]:
            td = t.get("thumbnail_deadline") or ""
            if td:
                td_date = _parse_deadline(td)
                if td_date:
                    days = (td_date - date.today()).days
                    if days < 0:
                        td = " | {}d overdue".format(abs(days))
                    elif days == 0:
                        td = " | due today"
                    else:
                        td = " | due {}".format(td_date.strftime("%b %d"))
            lines.append("- {}{}".format(t["display_name"], td))

    if thumb_data["in_revision"]:
        lines.append("")
        lines.append("**Sent Back to Ram ({}):**".format(len(thumb_data["in_revision"])))
        for t in thumb_data["in_revision"]:
            lines.append("- {}".format(t["display_name"]))

    if thumb_data.get("ram_slack_context"):
        lines.append("")
        lines.append("**Recent activity:**")
        for ctx in thumb_data["ram_slack_context"][:4]:
            lines.append("- {}".format(ctx))

    lines.append("")
    return lines


def format_action_report(all_editors, hours, all_tasks=None, silent_editors=None,
                         bench_editors=None, thumb_data=None):
    """Format report grouped by action needed (PM-optimized view)."""
    # Build tasks if not provided (backward compat)
    if all_tasks is None or silent_editors is None:
        all_tasks, silent_editors = _build_tasks_and_silent(all_editors)

    lines = []
    lines.append("## PM Action Report ({}h scan)".format(hours))
    lines.append("Generated: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M")))
    lines.append("")

    # Bucket tasks by status
    qc_tasks = [t for t in all_tasks if t["airtable_status"] in QC_STATUSES]
    schedule_tasks = [t for t in all_tasks if t["airtable_status"] == "80 - Approved By Client"]
    revision_tasks = [t for t in all_tasks if t["airtable_status"] == "59 - Editing Revisions"]
    client_tasks = [t for t in all_tasks if t["airtable_status"] == "75 - Sent to Client For Review"]
    in_progress = [t for t in all_tasks if t["airtable_status"] in (
        "41 - Sent to Editor", "50 - Editor Confirmed", "40 - Client Sent Raw Footage")]

    # DUE TODAY: videos with today/tomorrow deadline, excluding post-delivery
    due_today = [
        t for t in all_tasks
        if _days_until_deadline(t.get("deadline")) in (0, 1)
        and t["airtable_status"] not in POST_DEADLINE_STATUSES
    ]

    for bucket in (qc_tasks, schedule_tasks, revision_tasks, client_tasks, in_progress, due_today):
        bucket.sort(key=lambda t: t["display_name"])

    alerts = _detect_active_alerts(all_editors, all_tasks)

    # =====================================================================
    # CHECKLIST TOP — checkbox action items
    # =====================================================================

    # --- Deliver now (QC) ---
    if qc_tasks:
        lines.append("**Deliver now** (QC these videos):")
        for t in qc_tasks:
            dl = _deadline_display(t.get("deadline"), t["airtable_status"])
            dl_part = " | {}".format(dl) if dl else ""
            lines.append("- [ ] {} -- {}{}".format(t["display_name"], t["editor"], dl_part))
        lines.append("")

    # --- Schedule immediately ---
    if schedule_tasks:
        lines.append("**Schedule immediately** (client approved):")
        for t in schedule_tasks:
            waiting = ""
            lm = t.get("last_modified")
            if lm:
                try:
                    modified_dt = datetime.fromisoformat(lm.replace("Z", "+00:00"))
                    days_ago = (datetime.now(modified_dt.tzinfo) - modified_dt).days
                    waiting = " | waiting {}d".format(days_ago) if days_ago > 0 else " | approved today"
                except (ValueError, TypeError):
                    pass
            lines.append("- [ ] {} -- {}{}".format(t["display_name"], t["editor"], waiting))
        lines.append("")

    # --- Due today ---
    if due_today:
        lines.append("**Due today/tomorrow ({}):**".format(len(due_today)))
        for t in due_today:
            short_status = t["airtable_status"].split(" - ", 1)[-1] if " - " in t["airtable_status"] else t["airtable_status"]
            lines.append("- [ ] {} -- {} ({})".format(t["display_name"], t["editor"], short_status))
        lines.append("")

    # --- Follow up for approval (with client) ---
    if client_tasks:
        lines.append("**Follow up for approval** (with client):")
        for t in client_tasks:
            lines.append("- [ ] {} -- {}".format(t["display_name"], t["client"]))
        lines.append("")

    # --- Outreach (silent editors) ---
    if silent_editors:
        silent_editors.sort(key=lambda e: -e["active_videos"])
        lines.append("**Outreach** (silent editors):")
        for e in silent_editors:
            h = e.get("hours_since_last")
            if h is not None and h >= EDITOR_WHATSAPP_HOURS:
                action = "WhatsApp"
            elif h is not None and h >= EDITOR_NUDGE_HOURS:
                action = "Slack nudge"
            else:
                action = "check in"
            if h is not None:
                time_str = "{}h silent".format(int(h)) if h < 24 else "{}d silent".format(int(h / 24))
            else:
                time_str = "unknown"
            lines.append("- [ ] {} -- {} videos, {} ({})".format(
                e["editor"], e["active_videos"], time_str, action))
        lines.append("")

    # --- Unblock (blocked editors) ---
    blocked_tasks = [t for t in all_tasks if t.get("blockers")]
    if blocked_tasks:
        lines.append("**Unblock** (editors waiting on something):")
        for t in blocked_tasks:
            blocker_text = t["blockers"][0]["text"][:80]
            lines.append("- [ ] {} -- {}: \"{}\"".format(
                t["display_name"], t["editor"], blocker_text))
        lines.append("")

    # =====================================================================
    # DETAIL TABLES — structured data below the checklist
    # =====================================================================

    # --- ACTIVE ALERTS ---
    if alerts:
        lines.append("### ACTIVE ALERTS")
        lines.append("| Alert | Detail |")
        lines.append("|-------|--------|")
        for a in alerts:
            lines.append("| **{}** | {} |".format(a["alert"], a["detail"]))
        lines.append("")

    # --- FOLLOW UP (revisions) ---
    if revision_tasks:
        lines.append("### FOLLOW UP -- Editor Revisions ({})".format(len(revision_tasks)))
        lines.append("| # | Video | Editor | Deadline | Age | Last Activity |")
        lines.append("|---|-------|--------|----------|-----|---------------|")
        for i, t in enumerate(revision_tasks, 1):
            ctx = _get_latest_context_line(t)
            dl = _deadline_display(t.get("deadline"), t["airtable_status"])
            age = _status_age(t.get("last_modified"))
            lines.append("| {} | {} | {} | {} | {} | {} |".format(
                i, t["display_name"], t["editor"], dl, age, ctx
            ))
        lines.append("")

    # --- IN PROGRESS ---
    if in_progress:
        lines.append("### IN PROGRESS -- With Editors ({})".format(len(in_progress)))
        lines.append("| # | Video | Editor | Status | Deadline | Age |")
        lines.append("|---|-------|--------|--------|----------|-----|")
        for i, t in enumerate(in_progress, 1):
            short_status = t["airtable_status"].split(" - ", 1)[-1] if " - " in t["airtable_status"] else t["airtable_status"]
            dl = _deadline_display(t.get("deadline"), t["airtable_status"])
            age = _status_age(t.get("last_modified"))
            lines.append("| {} | {} | {} | {} | {} | {} |".format(
                i, t["display_name"], t["editor"], short_status, dl, age
            ))
        lines.append("")

    # --- BENCH ---
    lines.extend(_format_bench_section(bench_editors))

    # --- RAM ---
    lines.extend(_format_ram_section(thumb_data))

    # Totals
    total = len(all_tasks)
    lines.append("---")
    lines.append("**{} videos tracked across {} editors.**".format(total, len(all_editors)))
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
    elif status in QC_STATUSES:
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
    # NOTE: --editors-only is intentionally undocumented in Simon's CLAUDE.md.
    # Idle editors appear in the BENCH section which is useful context for assignments.
    # Parallel Slack fetching makes the speed gain negligible. Consider removing entirely.
    parser.add_argument("--editors-only", action="store_true", default=False,
                        help="Only show editors with active Airtable videos")
    parser.add_argument("--format", choices=["editor", "action"], default="action",
                        dest="report_format",
                        help="Report format: 'action' (prioritized PM view) or 'editor' (per-editor deep dive)")

    args = parser.parse_args()

    try:
        # Phase 0: Discover editor channels from Slack + Airtable Team table
        global EDITOR_CHANNELS
        EDITOR_CHANNELS = discover_editor_channels()
        print(f"  Matched {len(EDITOR_CHANNELS)} editor(s)", file=sys.stderr)

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
        print(f"\nPhase 2: Reading {len(editors_to_process)} editor channel(s) in parallel...", file=sys.stderr)
        all_editors = []

        editors_list = [
            (editor_key, channel_info)
            for editor_key, channel_info in sorted(editors_to_process.items())
            if not (args.editors_only and not pipeline.get(editor_key, []))
        ]

        def _fetch_editor(editor_key, channel_info):
            return editor_key, get_slack_activity(channel_info["id"], args.hours)

        slack_by_editor = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(_fetch_editor, ek, ci): ek
                for ek, ci in editors_list
            }
            for future in as_completed(futures):
                editor_key, msgs = future.result()
                slack_by_editor[editor_key] = msgs

        for editor_key, channel_info in editors_list:
            airtable_videos = pipeline.get(editor_key, [])
            slack_messages = slack_by_editor.get(editor_key, [])
            print(f"  #{channel_info['name']}: {len(slack_messages)} messages, {len(airtable_videos)} Airtable videos", file=sys.stderr)
            editor_data = analyze_editor(editor_key, slack_messages, airtable_videos)
            all_editors.append(editor_data)

        # Phase 3: Output
        print(f"\nPhase 3: Generating report...", file=sys.stderr)

        # Build shared task list and silent editors
        all_tasks, silent_editors = _build_tasks_and_silent(all_editors)

        # Bench + thumbnail analysis (skip in single-editor mode)
        bench_editors = None
        thumb_data = None
        if not args.editor:
            print("  Detecting bench editors...", file=sys.stderr)
            bench_editors = detect_bench_editors(pipeline, all_editors)
            print(f"  {len(bench_editors)} editors on bench", file=sys.stderr)

            print("  Analyzing thumbnail pipeline...", file=sys.stderr)
            thumb_data = analyze_thumbnail_pipeline(all_tasks)
            print(f"  {thumb_data['total_queue']} thumbnails in queue", file=sys.stderr)

            # Try to get Ram's Slack context (bonus, not required)
            ram_context = _get_ram_slack_context(args.hours)
            if ram_context:
                thumb_data["ram_slack_context"] = ram_context
                print(f"  {len(ram_context)} Ram Slack messages found", file=sys.stderr)

        if args.output == "json":
            output = {
                "generated": datetime.now().isoformat(),
                "hours_scanned": args.hours,
                "report_format": args.report_format,
                "editors": all_editors,
            }
            if bench_editors is not None:
                output["bench_editors"] = bench_editors
            if thumb_data is not None:
                output["thumbnail_pipeline"] = thumb_data
            print(json.dumps(output, indent=2, default=str))
        elif args.report_format == "action":
            report = format_action_report(all_editors, args.hours,
                                          all_tasks=all_tasks,
                                          silent_editors=silent_editors,
                                          bench_editors=bench_editors,
                                          thumb_data=thumb_data)
            print(report)
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
