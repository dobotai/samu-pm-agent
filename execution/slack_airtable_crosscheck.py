#!/usr/bin/env python3
"""
Slack-Airtable Cross-Check Tool
Targeted checks that catch things that actually slip through cracks.

Nine checks:
1. new_footage      -- Client mentioned recording in Slack but no Airtable assignment
2. client_approval  -- Client may have approved in Slack but Airtable still at 75
3. thumbnail_blockers -- Video ready but thumbnail not approved (zero ambiguity)
4. unanswered       -- Client asked a question/request but no team reply (4+ hours)
5. gaps             -- Editor channels with active videos but zero messages
6. stale            -- Videos stuck at the same status past expected thresholds
7. deliverables     -- Monthly video delivery count vs package commitment
8. assignments      -- Clients with remaining deliverables but 0 active videos
9. pm_tasks         -- Tasks Samu posted in #project-management with no Simon reply yet

Usage:
    python execution/slack_airtable_crosscheck.py
    python execution/slack_airtable_crosscheck.py --check new_footage
    python execution/slack_airtable_crosscheck.py --check thumbnail_blockers
    python execution/slack_airtable_crosscheck.py --check pm_tasks
    python execution/slack_airtable_crosscheck.py --hours 72
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
load_dotenv()

# Shared helpers (same pattern as editor_task_report / client_status_report)
sys.path.insert(0, os.path.dirname(__file__))
from airtable_read import read_airtable_records
from slack_read_channel import read_slack_channel
from slack_list_channels import list_slack_channels
from client_status_report import get_team_slack_ids, needs_response

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
from utils import format_video_ref, get_client_map, resolve_editor_name, get_editor_map
from constants import (
    QC_STATUSES, POST_DEADLINE_STATUSES, INACTIVE_CLIENT_STATUSES,
    ALL_ACTIVE_STATUSES, STATUS_ORDER, STATUS_STALE_DAYS,
    THUMBNAIL_ACTIVE_STATUSES,
    APPROVAL_KEYWORDS, FOOTAGE_KEYWORDS,
    SAMU_SLACK_USER_ID, SIMON_SLACK_USER_ID,
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
            "Thumbnail Status",
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


def _get_client_channels():
    """Get all *-client Slack channels. Returns list of {id, name, client_name}."""
    try:
        channels = list_slack_channels(filter_pattern="-client")
    except Exception:
        return []

    result = []
    for ch in channels:
        if ch.get("is_archived"):
            continue
        name = ch["name"]
        # Derive client name: "jamal-client" -> "Jamal"
        client_name = name.replace("-client", "").replace("-", " ").title()
        result.append({
            "id": ch["id"],
            "name": name,
            "client_name": client_name,
        })
    return result


def _prefetch_client_channels(client_channels, hours, include_threads=False, max_threads_val=0, extra_channels=None, extra_hours=None):
    """Fetch all client channel messages in parallel. Returns {channel_id: messages}."""
    cache = {}
    targets = list(client_channels)
    if extra_channels:
        targets = targets + [ch for ch in extra_channels if ch not in {c["id"] for c in client_channels}]

    def _fetch(ch):
        ch_id = ch["id"] if isinstance(ch, dict) else ch
        try:
            msgs = read_slack_channel(ch_id, since_hours=hours, include_threads=include_threads, max_threads=max_threads_val)
            return ch_id, msgs
        except Exception:
            return ch_id, []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch, ch): ch for ch in targets}
        for future in as_completed(futures):
            ch_id, msgs = future.result()
            cache[ch_id] = msgs

    return cache


def _match_client_to_channel(client_name, client_channels):
    """Find matching client channel by fuzzy name comparison."""
    if not client_name:
        return None
    cn_lower = client_name.lower().strip()
    for ch in client_channels:
        ch_lower = ch["client_name"].lower().strip()
        # Exact match or one contains the other
        if cn_lower == ch_lower or cn_lower in ch_lower or ch_lower in cn_lower:
            return ch
    return None


# ---------------------------------------------------------------------------
# Check 1: New footage (replaces old status discrepancy)
# ---------------------------------------------------------------------------

def check_new_footage(active_videos, client_map, client_channels, team_slack_ids=None, hours=48, channel_cache=None):
    """Find clients who mentioned recording in Slack but have no video at status 40/41.

    Only flags messages from the client (non-team senders) to avoid catching
    team nudges like 'let us know when uploaded'.
    """
    # Build set of clients that already have a video at 40 or 41
    clients_with_assignment = set()
    for v in active_videos:
        fields = v["fields"]
        status = fields.get("Editing Status", "")
        if status in ("40 - Client Sent Raw Footage", "41 - Sent to Editor"):
            client_ids = fields.get("Client", [])
            if client_ids:
                cid = client_ids[0] if isinstance(client_ids, list) else client_ids
                name = client_map.get(cid, "")
                if name:
                    clients_with_assignment.add(name.lower())

    findings = []

    for ch in client_channels:
        # Skip if client already has footage assigned
        if ch["client_name"].lower() in clients_with_assignment:
            continue

        if channel_cache is not None:
            messages = channel_cache.get(ch["id"], [])
        else:
            try:
                messages = read_slack_channel(ch["id"], since_hours=hours, include_threads=False, max_threads=0)
            except Exception:
                continue

        if not messages:
            continue

        # Find the most recent matching message for this client
        latest = None
        for msg in messages:
            # Only flag messages from the client, not from team members
            if team_slack_ids and msg.get("user_id", "") in team_slack_ids:
                continue

            text = msg.get("text", "").lower()
            for keyword in FOOTAGE_KEYWORDS:
                if keyword in text:
                    # Skip if context shows client is forwarding to a third party,
                    # not submitting raw footage to us (e.g. "I sent it to the sponsor")
                    false_positive_patterns = [
                        "to the sponsor", "to sponsor", "to my sponsor",
                        "to the client", "to their team", "to my team",
                        "to the brand", "to my producer", "to their",
                        "waiting on them", "waiting for them", "waiting for approval",
                        "waiting on the",
                        "for approval", "for their review",
                        "sponsor for", "approval from",
                    ]
                    if any(fp in text for fp in false_positive_patterns):
                        break
                    latest = msg
                    break  # one finding per message is enough

        if latest:
            findings.append({
                "client": ch["client_name"],
                "message": latest.get("text", "")[:120].replace("|", "/"),
                "when": latest.get("datetime", "")[:16],
                "channel": ch["name"],
            })

    return findings


# ---------------------------------------------------------------------------
# Check 2: Client approval
# ---------------------------------------------------------------------------

def check_client_approval(active_videos, client_map, client_channels, hours=72,
                          channel_cache=None, team_slack_ids=None):
    """Find clients who may have approved a video in Slack but Airtable still at 75.

    Filters:
      - Only matches messages from the client (not team members).
      - Skips messages that look like questions (contain '?') since
        "go ahead?" or "looks good?" is asking, not confirming.
      - Shows which video(s) at 75 the approval might apply to.
    """
    # Group videos at status 75 by client name, keeping video numbers for matching
    client_videos_at_75: dict[str, list[dict]] = {}
    for v in active_videos:
        fields = v["fields"]
        status = fields.get("Editing Status", "")
        if status != "75 - Sent to Client For Review":
            continue

        client_ids = fields.get("Client", [])
        if not client_ids:
            continue
        cid = client_ids[0] if isinstance(client_ids, list) else client_ids
        name = client_map.get(cid, "")
        if not name:
            continue

        ref = format_video_ref(fields, client_map)
        vid_num = str(fields.get("Video Number", ""))
        client_videos_at_75.setdefault(name, []).append({"ref": ref, "num": vid_num})

    if not client_videos_at_75:
        return []

    findings = []
    _team_ids = team_slack_ids or set()

    for client_name, video_info_list in client_videos_at_75.items():
        ch = _match_client_to_channel(client_name, client_channels)
        if not ch:
            continue

        if channel_cache is not None:
            messages = channel_cache.get(ch["id"], [])
        else:
            try:
                messages = read_slack_channel(ch["id"], since_hours=hours, include_threads=True, max_threads=10)
            except Exception:
                continue

        if not messages:
            continue

        video_refs = [vi["ref"] for vi in video_info_list]

        def _check_for_approval(msg):
            # Only match client messages, not team
            if _team_ids and msg.get("user_id", "") in _team_ids:
                return False
            text = msg.get("text", "")
            text_lower = text.lower()
            # Skip messages that are questions, not confirmations.
            # Literal "?" or question-framing phrases like "do we", "should we",
            # "or we", "if we", "can we" near approval keywords.
            if "?" in text:
                return False
            question_frames = [
                "do we", "should we", "or we", "if we", "can we",
                "shall we", "would we", "could we",
                "do i", "should i", "or i", "if i", "can i",
            ]
            if any(qf in text_lower for qf in question_frames):
                return False
            for keyword in APPROVAL_KEYWORDS:
                if keyword in text_lower:
                    # Try to figure out which video number the approval references
                    matched_refs = []
                    for vi in video_info_list:
                        if vi["num"] and (
                            f"video {vi['num']}" in text_lower
                            or f"#{vi['num']}" in text_lower
                            or f"vid {vi['num']}" in text_lower
                        ):
                            matched_refs.append(vi["ref"])
                    # If no specific video mentioned, show all at 75
                    display_refs = matched_refs if matched_refs else video_refs

                    findings.append({
                        "client": client_name,
                        "videos_at_75": ", ".join(display_refs),
                        "message": text[:120].replace("|", "/"),
                        "when": msg.get("datetime", "")[:16],
                        "matched_specific": bool(matched_refs),
                    })
                    return True
            return False

        for msg in messages:
            if _check_for_approval(msg):
                break  # one finding per client is enough
            for reply in msg.get("thread_replies", []):
                if _check_for_approval(reply):
                    break

    return findings


# ---------------------------------------------------------------------------
# Check 3: Thumbnail blockers
# ---------------------------------------------------------------------------

def check_thumbnail_blockers(active_videos, client_map, editor_map):
    """Find videos at 70/75/80 where thumbnail is not approved.

    Skips Short-Form videos -- shorts don't have custom thumbnails.
    """
    blockers = []
    target_statuses = [
        "70 - Approved By Agency",
        "75 - Sent to Client For Review",
        "80 - Approved By Client",
    ]

    for v in active_videos:
        fields = v["fields"]
        status = fields.get("Editing Status", "")
        if status not in target_statuses:
            continue

        # Shorts and VSLs don't have thumbnails -- skip them
        fmt = str(fields.get("Format", "")).lower()
        if "short" in fmt or "vsl" in fmt:
            continue

        thumb_status = fields.get("Thumbnail Status", "")
        if not thumb_status or thumb_status in THUMBNAIL_ACTIVE_STATUSES:
            blockers.append({
                "video": format_video_ref(fields, client_map),
                "video_status": status.split(" - ", 1)[-1] if " - " in status else status,
                "thumbnail_status": thumb_status or "(not set)",
                "editor": resolve_editor_name(fields, editor_map),
            })

    return blockers


# ---------------------------------------------------------------------------
# Check 4: Stale client input
# ---------------------------------------------------------------------------

def check_stale_input(client_map, client_channels, team_slack_ids=None, channel_cache=None):
    """Find videos at 'Waiting For Input From Client' for too long.

    Shows who sent the last message and flags if team is actively engaged
    (so Simon doesn't waste time following up on something already being handled).
    """
    # Fetch videos at waiting status
    waiting_videos = read_airtable_records(
        "Videos",
        filter_formula="{Editing Status} = 'Waiting For Input From Client'",
        fields=[
            "Video Number", "Client", "Editing Status",
            "Last Modified (Editing Status)",
        ],
    )

    if not waiting_videos:
        return []

    now = datetime.now()
    findings = []

    for v in waiting_videos:
        fields = v["fields"]
        lm = fields.get("Last Modified (Editing Status)", "")
        if not lm:
            continue

        try:
            modified_dt = datetime.fromisoformat(lm.replace("Z", "+00:00"))
            days_waiting = (now.astimezone(modified_dt.tzinfo) - modified_dt).days
        except (ValueError, TypeError):
            continue

        if days_waiting < STALE_INPUT_DAYS:
            continue

        # Resolve client name
        client_ids = fields.get("Client", [])
        client_name = ""
        if client_ids:
            cid = client_ids[0] if isinstance(client_ids, list) else client_ids
            client_name = client_map.get(cid, "Unknown")

        video_num = str(fields.get("Video Number", "?"))

        # Try to get last message for context -- show WHO sent it
        last_msg = ""
        last_msg_when = ""
        last_msg_from = ""
        team_active = False
        ch = _match_client_to_channel(client_name, client_channels)
        if ch:
            try:
                if channel_cache is not None:
                    messages = channel_cache.get(ch["id"], [])
                else:
                    messages = read_slack_channel(ch["id"], since_hours=24*30, include_threads=False, max_threads=0, limit=10)
                if messages:
                    # Most recent message
                    recent = messages[0]
                    last_msg = recent.get("text", "")[:80].replace("|", "/")
                    last_msg_when = recent.get("datetime", "")[:16]
                    last_msg_from = recent.get("user", "Unknown")

                    # Check if team has been active in last 48h
                    if team_slack_ids:
                        for msg in messages[:5]:
                            uid = msg.get("user_id", "")
                            msg_ts = float(msg.get("timestamp", "0"))
                            hours_ago = (now - datetime.fromtimestamp(msg_ts)).total_seconds() / 3600
                            if uid in team_slack_ids and hours_ago < 48:
                                team_active = True
                                break
            except Exception:
                pass

        findings.append({
            "client": client_name,
            "video": f"{client_name} #{video_num}",
            "days_waiting": days_waiting,
            "last_message": last_msg or "(no recent messages)",
            "last_msg_from": last_msg_from,
            "last_msg_when": last_msg_when or "N/A",
            "team_active": team_active,
        })

    findings.sort(key=lambda f: -f["days_waiting"])
    return findings


# ---------------------------------------------------------------------------
# Check 5: Unanswered client messages
# ---------------------------------------------------------------------------

def check_unanswered(client_channels, team_slack_ids, hours=72, channel_cache=None):
    """Find client channels where the client asked something and no team member replied.

    Reuses needs_response() and team detection from client_status_report.
    Only flags messages 4+ hours old without a team reply or team reaction.
    """
    findings = []

    for ch in client_channels:
        if channel_cache is not None:
            messages = channel_cache.get(ch["id"], [])
        else:
            try:
                messages = read_slack_channel(ch["id"], since_hours=hours, include_threads=True, max_threads=10)
            except Exception:
                continue

        if not messages:
            continue

        # Flatten messages + thread replies into chronological order
        expanded = []
        for msg in messages:
            expanded.append(msg)
            for reply in msg.get("thread_replies", []):
                expanded.append(reply)
        sorted_msgs = sorted(expanded, key=lambda m: float(m.get("timestamp", "0")))

        # Walk through and find unanswered client messages
        pending_client_msg = None
        pending_client_time = None

        for msg in sorted_msgs:
            user_id = msg.get("user_id", "unknown")
            if user_id == "unknown":
                continue

            ts = float(msg.get("timestamp", "0"))
            msg_time = datetime.fromtimestamp(ts)
            is_team = user_id in team_slack_ids

            if is_team:
                # Team replied -- clear pending
                pending_client_msg = None
                pending_client_time = None
            else:
                text = msg.get("text", "")
                if needs_response(text):
                    pending_client_msg = msg
                    pending_client_time = msg_time

        # Check if there's a trailing unanswered message
        if pending_client_msg and pending_client_time:
            # Check for team reactions (emoji acknowledgment counts)
            team_reacted = False
            for reaction in pending_client_msg.get("reactions", []):
                reactors = set(reaction.get("users", []))
                if reactors & team_slack_ids:
                    team_reacted = True
                    break

            if not team_reacted:
                hours_ago = (datetime.now() - pending_client_time).total_seconds() / 3600
                if hours_ago >= 4:
                    findings.append({
                        "client": ch["client_name"],
                        "message": pending_client_msg.get("text", "")[:120].replace("|", "/"),
                        "user": pending_client_msg.get("user", "Unknown"),
                        "hours_ago": round(hours_ago, 1),
                        "when": pending_client_time.strftime("%Y-%m-%d %H:%M"),
                        "channel": ch["name"],
                    })

    findings.sort(key=lambda f: -f["hours_ago"])
    return findings


# ---------------------------------------------------------------------------
# Check 6: Communication gaps (existing)
# ---------------------------------------------------------------------------

def check_communication_gaps(active_videos, client_map, editor_map, hours=72):
    """Find editor channels with active videos but zero messages."""
    channel_videos = {}
    for v in active_videos:
        fields = v["fields"]
        status = fields.get("Editing Status", "")

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

    # Fetch all editor channels in parallel
    def _fetch_editor(ch_id):
        try:
            return ch_id, read_slack_channel(ch_id, since_hours=hours, include_threads=True, max_threads=10)
        except Exception:
            return ch_id, []

    editor_messages = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_editor, ch_id): ch_id for ch_id in channel_videos}
        for future in as_completed(futures):
            ch_id, msgs = future.result()
            editor_messages[ch_id] = msgs

    for ch_id, videos in channel_videos.items():
        messages = editor_messages.get(ch_id, [])
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
# Check 6: Stale statuses (existing)
# ---------------------------------------------------------------------------

def check_stale_statuses(active_videos, client_map, editor_map):
    """Find videos stuck at the same status for too long."""
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
# Check 7: Client deliverables (existing)
# ---------------------------------------------------------------------------

def _parse_deliverables(raw_str):
    """Parse a deliverables string into structured counts."""
    if not raw_str:
        return {"long_form": 0, "shorts": 0, "total": 0}

    text = str(raw_str).lower()
    text = re.sub(r"\b(720|1080|2160|4k)\w*", "", text)

    long_form = 0
    shorts = 0

    shorts_match = re.search(r"(\d+)\s*(?:short|shorts|short-form)", text)
    if shorts_match:
        shorts = int(shorts_match.group(1))

    long_match = re.search(r"(\d+)\s*(?:long-form|long|videos?|/mo)", text)
    if long_match:
        long_form = int(long_match.group(1))
    elif not shorts_match:
        package_keywords = re.search(r"video|/mo|per month|monthly|long-form|short-form", text)
        if package_keywords:
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

        if info["status"] in INACTIVE_CLIENT_STATUSES:
            continue

        name = info["name"]
        if name not in client_counts:
            client_counts[name] = {
                "delivered": 0,
                "active": 0,
                "deliverables_raw": info.get("deliverables", ""),
            }

        if status and "100 -" not in status and "DONE" not in status:
            client_counts[name]["active"] += 1

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

    results = []
    for name, counts in sorted(client_counts.items()):
        parsed = _parse_deliverables(counts["deliverables_raw"])
        package_total = parsed["total"]

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
# Check 8: Assignment gaps (existing)
# ---------------------------------------------------------------------------

def check_assignment_gaps(deliverables_results):
    """Find clients with remaining deliverables but zero active videos."""
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
# Check 9: Outstanding PM tasks from Samu in #project-management
# ---------------------------------------------------------------------------

# Phrases that signal Samu is directing a task at Simon.
# Kept tight to avoid matching conversational fragments like "we need to
# turn that ship around" or "nah we can just send it".
_TASK_SIGNAL_PHRASES = [
    "can you", "could you", "please", "pls", "make sure", "don't forget",
    "remember to", "need you to", "follow up", "check on",
    "reach out", "remind", "let me know",
    "when you get a chance",
    "priority for today", "priority is", "vid priority",
]

# Imperative starters: match only at beginning of message.
_IMPERATIVE_STARTERS = [
    "schedule ", "assign ", "send ", "add ", "fix ", "update ",
    "check ", "ping ", "reach ", "follow ", "remind ", "review ",
    "look ", "message ", "move ", "set ", "confirm ", "clear ",
    "handle ", "take ", "make ", "onboard ",
    "connect ", "coordinate ", "train ", "double check ", "double-check ",
]

# Seconds within which consecutive Samu messages are grouped into one task.
_CLUSTER_WINDOW_SECONDS = 300  # 5 minutes

# Seconds after a Samu message within which a Simon in-channel message
# counts as a response (even without a thread reply or reaction).
_INCHANNEL_REPLY_WINDOW = 600  # 10 minutes


def _looks_like_task(text: str) -> bool:
    """Return True if the message text looks like an actionable task for Simon."""
    stripped = text.strip()
    # Samu uses -----\n as a deliberate task separator — always a task
    if stripped.startswith("-----") or stripped.startswith("----"):
        return True
    # Direct @mention of Simon is always a task
    if f"<@{SIMON_SLACK_USER_ID}>" in stripped:
        return True

    lower = text.lower()
    for phrase in _TASK_SIGNAL_PHRASES:
        if phrase in lower:
            return True
    for starter in _IMPERATIVE_STARTERS:
        if lower.startswith(starter):
            return True
    return False


def _simon_responded(msg, simon_id: str, all_messages: list) -> bool:
    """Return True if Simon replied in thread, reacted, or replied in-channel.

    In-channel reply: Simon sent a message within _INCHANNEL_REPLY_WINDOW
    seconds after the Samu message in the flat channel timeline.
    """
    # Check thread replies
    for reply in msg.get("thread_replies", []):
        if reply.get("user_id") == simon_id:
            return True
    # Check reactions from Simon
    for reaction in msg.get("reactions", []):
        if simon_id in reaction.get("users", []):
            return True
    # Check in-channel reply within time window
    msg_ts = float(msg.get("timestamp", "0"))
    window_end = msg_ts + _INCHANNEL_REPLY_WINDOW
    for other in all_messages:
        if other.get("user_id") != simon_id:
            continue
        other_ts = float(other.get("timestamp", "0"))
        if msg_ts < other_ts <= window_end:
            return True
    return False


def _cluster_tasks(raw_tasks: list) -> list:
    """Group Samu task messages within _CLUSTER_WINDOW_SECONDS into one entry.

    Picks the most representative message per cluster: @Simon mention first,
    then dash-separator, then the longest (most specific) message.
    Returns list of {message, when, hours_ago, count}.
    """
    if not raw_tasks:
        return []

    sorted_tasks = sorted(raw_tasks, key=lambda t: t["timestamp"])

    clusters: list[list] = []
    current: list = [sorted_tasks[0]]

    for task in sorted_tasks[1:]:
        if task["timestamp"] - current[-1]["timestamp"] <= _CLUSTER_WINDOW_SECONDS:
            current.append(task)
        else:
            clusters.append(current)
            current = [task]
    clusters.append(current)

    result = []
    for cluster in clusters:
        # Pick best representative
        best = None
        for msg in cluster:
            text = msg["text"]
            if f"<@{SIMON_SLACK_USER_ID}>" in text:
                best = msg
                break
            if text.strip().startswith("----"):
                best = msg
                break
        if not best:
            best = max(cluster, key=lambda m: len(m["text"]))

        result.append({
            "message": best["text"][:160].replace("|", "/"),
            "when": best["when"],
            "hours_ago": best["hours_ago"],
            "count": len(cluster),
        })

    # Most recent first
    result.sort(key=lambda t: t["hours_ago"])
    return result


def check_pm_tasks(hours: int = 72) -> list:
    """Scan #project-management for tasks Samu gave Simon that are still open.

    Looks back `hours` hours.  For each Samu message that looks like an
    action item, checks whether Simon replied (in-thread, in-channel within
    10 min, or via reaction).  Clusters nearby messages (within 5 min) into
    a single task entry to avoid counting conversation fragments separately.
    """
    try:
        messages = read_slack_channel(
            "#project-management",
            limit=200,
            since_hours=hours,
            include_threads=True,
            max_threads=100,
        )
    except Exception:
        return []

    raw_tasks = []
    now = datetime.now()

    for msg in messages:
        if msg.get("user_id") != SAMU_SLACK_USER_ID:
            continue

        text = msg.get("text", "").strip()
        if not text or not _looks_like_task(text):
            continue

        # Skip if Simon already responded (thread, reaction, or in-channel)
        if _simon_responded(msg, SIMON_SLACK_USER_ID, messages):
            continue

        ts = float(msg.get("timestamp", "0"))
        hours_ago = (now - datetime.fromtimestamp(ts)).total_seconds() / 3600

        raw_tasks.append({
            "text": text,
            "message": text[:160].replace("|", "/"),
            "when": msg.get("datetime", "")[:16],
            "hours_ago": round(hours_ago, 1),
            "timestamp": ts,
        })

    return _cluster_tasks(raw_tasks)


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

    # New footage
    if "new_footage" in results:
        items = results["new_footage"]
        lines.append(f"### Unassigned Footage ({len(items)} found)")
        if items:
            lines.append("| Client | Message | When | Channel |")
            lines.append("|--------|---------|------|---------|")
            for f in items:
                lines.append(
                    f"| {f['client']} | \"{f['message'][:60]}\" | {f['when']} | #{f['channel']} |"
                )
        else:
            lines.append("No unassigned footage detected.")
        lines.append("")

    # Client approval
    if "client_approval" in results:
        items = results["client_approval"]
        lines.append(f"### Possible Client Approvals ({len(items)} found)")
        if items:
            lines.append("*Verify before updating Airtable -- these are keyword matches, not conclusions.*")
            lines.append("")
            lines.append("| Client | Video(s) at 75 | Message | When |")
            lines.append("|--------|---------------|---------|------|")
            for a in items:
                vid_col = a["videos_at_75"]
                if not a.get("matched_specific"):
                    vid_col += " (verify #)"
                lines.append(
                    f"| {a['client']} | {vid_col} "
                    f"| \"{a['message'][:60]}\" | {a['when']} |"
                )
        else:
            lines.append("No approval signals found.")
        lines.append("")

    # Thumbnail blockers
    if "thumbnail_blockers" in results:
        items = results["thumbnail_blockers"]
        lines.append(f"### Thumbnail Blockers ({len(items)} found)")
        if items:
            lines.append("| Video | Video Status | Thumbnail Status | Editor |")
            lines.append("|-------|-------------|-----------------|--------|")
            for t in items:
                lines.append(
                    f"| {t['video']} | {t['video_status']} "
                    f"| {t['thumbnail_status']} | {t['editor']} |"
                )
        else:
            lines.append("All thumbnails are on track.")
        lines.append("")

    # Unanswered
    if "unanswered" in results:
        items = results["unanswered"]
        lines.append(f"### Unanswered Client Messages ({len(items)} found)")
        if items:
            lines.append("*Client asked a question or made a request with no team reply.*")
            lines.append("")
            lines.append("| Client | Message | From | Hours Ago | When |")
            lines.append("|--------|---------|------|----------|------|")
            for u in items:
                lines.append(
                    f"| {u['client']} | \"{u['message'][:60]}\" "
                    f"| {u['user']} | {u['hours_ago']}h | {u['when']} |"
                )
        else:
            lines.append("All client messages have been responded to.")
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

    # PM tasks from Samu
    if "pm_tasks" in results:
        items = results["pm_tasks"]
        total_msgs = sum(t.get("count", 1) for t in items)
        lines.append(f"### Outstanding Tasks from Samu ({len(items)} tasks from {total_msgs} messages)")
        if items:
            lines.append("*Tasks Samu posted in #project-management with no Simon reply or reaction yet.*")
            lines.append("*Nearby messages (within 5 min) grouped into single tasks.*")
            lines.append("")
            lines.append("| # | Task | When | Hours Ago | Msgs |")
            lines.append("|---|------|------|-----------|------|")
            for i, t in enumerate(items, 1):
                count = t.get("count", 1)
                count_str = str(count) if count > 1 else ""
                lines.append(
                    f"| {i} | \"{t['message'][:80]}\" | {t['when']} | {t['hours_ago']}h | {count_str} |"
                )
        else:
            lines.append("All Samu tasks have been acknowledged.")
        lines.append("")

    # Recommended Actions
    recommendations = []
    if results.get("new_footage"):
        n = len(results["new_footage"])
        recommendations.append(f"Check {n} possible new footage mention{'s' if n != 1 else ''} in client channels")
    if results.get("client_approval"):
        n = len(results["client_approval"])
        recommendations.append(f"Verify {n} possible client approval{'s' if n != 1 else ''}")
    if results.get("thumbnail_blockers"):
        n = len(results["thumbnail_blockers"])
        recommendations.append(f"Resolve {n} thumbnail blocker{'s' if n != 1 else ''}")
    if results.get("unanswered"):
        n = len(results["unanswered"])
        recommendations.append(f"Reply to {n} unanswered client message{'s' if n != 1 else ''}")
    if results.get("communication_gaps"):
        n = len(results["communication_gaps"])
        recommendations.append(f"Follow up with {n} silent editor{'s' if n != 1 else ''}")
    if results.get("stale_statuses"):
        n = len(results["stale_statuses"])
        recommendations.append(f"Check {n} stale video{'s' if n != 1 else ''}")
    if results.get("assignment_gaps"):
        n = len(results["assignment_gaps"])
        recommendations.append(f"Assign videos for {n} client{'s' if n != 1 else ''} behind on deliverables")
    if results.get("pm_tasks"):
        n = len(results["pm_tasks"])
        recommendations.append(f"Complete {n} outstanding task{'s' if n != 1 else ''} from Samu in #project-management")

    if recommendations:
        lines.append("### Recommended Actions")
        for i, r in enumerate(recommendations, 1):
            lines.append(f"{i}. {r}")
        lines.append("")

    # Summary line
    lines.append("---")
    summary_parts = []
    for key, singular, plural in [
        ("new_footage", "footage flag", "footage flags"),
        ("client_approval", "approval signal", "approval signals"),
        ("thumbnail_blockers", "thumbnail blocker", "thumbnail blockers"),
        ("unanswered", "unanswered message", "unanswered messages"),
        ("communication_gaps", "silent editor", "silent editors"),
        ("stale_statuses", "stale status", "stale statuses"),
        ("assignment_gaps", "assignment gap", "assignment gaps"),
        ("pm_tasks", "Samu task", "Samu tasks"),
    ]:
        if key in results:
            n = len(results[key])
            if n > 0:
                summary_parts.append(f"{n} {plural if n != 1 else singular}")
    if summary_parts:
        lines.append(f"**{', '.join(summary_parts)}.**")
    else:
        lines.append("**All clear.**")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cross-check Slack and Airtable data")
    parser.add_argument(
        "--check",
        choices=[
            "all", "new_footage", "client_approval", "thumbnail_blockers",
            "unanswered", "gaps", "stale", "deliverables",
            "assignments", "pm_tasks",
        ],
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
    check = args.check

    try:
        # Phase 1: Fetch all independent data sources in parallel
        print("Phase 1: Fetching data in parallel...", file=sys.stderr)

        needs_active = check in ("all", "new_footage", "client_approval",
                                  "thumbnail_blockers", "gaps", "stale")
        needs_client_channels = check in ("all", "new_footage", "client_approval", "unanswered")
        needs_team_ids = check in ("all", "unanswered", "new_footage", "client_approval")

        fetch_tasks = {"client_map": get_client_map, "editor_map": get_editor_map}
        if needs_active:
            fetch_tasks["active_videos"] = get_active_videos
        if needs_client_channels:
            fetch_tasks["client_channels"] = _get_client_channels
        if needs_team_ids:
            fetch_tasks["team_slack_ids"] = get_team_slack_ids

        fetched = {}
        with ThreadPoolExecutor(max_workers=len(fetch_tasks)) as executor:
            futures = {executor.submit(fn): key for key, fn in fetch_tasks.items()}
            for future in as_completed(futures):
                key = futures[future]
                fetched[key] = future.result()

        client_map = fetched["client_map"]
        editor_map = fetched["editor_map"]
        active_videos = fetched.get("active_videos", [])
        client_channels = fetched.get("client_channels", [])
        team_slack_ids = fetched.get("team_slack_ids", set())

        print(f"  Done ({len(active_videos)} videos, {len(client_channels)} client channels)", file=sys.stderr)

        # Pre-fetch all client channel messages in parallel
        channel_cache = None
        if client_channels:
            print(f"Pre-fetching {len(client_channels)} client channels in parallel...", file=sys.stderr)
            channel_cache = _prefetch_client_channels(
                client_channels, hours=args.hours,
                include_threads=True, max_threads_val=10,
            )
            print(f"  Done ({len(channel_cache)} channels fetched)", file=sys.stderr)

        results = {}

        # Phase 2: Run checks
        if check in ("all", "new_footage"):
            print("Checking new footage...", file=sys.stderr)
            results["new_footage"] = check_new_footage(
                active_videos, client_map, client_channels, team_slack_ids, args.hours,
                channel_cache=channel_cache,
            )

        if check in ("all", "client_approval"):
            print("Checking client approvals...", file=sys.stderr)
            results["client_approval"] = check_client_approval(
                active_videos, client_map, client_channels, args.hours,
                channel_cache=channel_cache,
                team_slack_ids=team_slack_ids,
            )

        if check in ("all", "thumbnail_blockers"):
            print("Checking thumbnail blockers...", file=sys.stderr)
            results["thumbnail_blockers"] = check_thumbnail_blockers(
                active_videos, client_map, editor_map
            )

        if check in ("all", "unanswered"):
            print("Checking unanswered client messages...", file=sys.stderr)
            results["unanswered"] = check_unanswered(
                client_channels, team_slack_ids, args.hours,
                channel_cache=channel_cache,
            )

        if check in ("all", "gaps"):
            print("Checking communication gaps...", file=sys.stderr)
            results["communication_gaps"] = check_communication_gaps(
                active_videos, client_map, editor_map, args.hours
            )

        if check in ("all", "stale"):
            print("Checking stale statuses...", file=sys.stderr)
            results["stale_statuses"] = check_stale_statuses(
                active_videos, client_map, editor_map
            )

        if check in ("all", "deliverables", "assignments"):
            print("Checking client deliverables...", file=sys.stderr)
            client_info = get_client_info()
            all_videos = get_all_videos()
            deliverables = check_client_deliverables(all_videos, client_info)
            if check in ("all", "deliverables"):
                results["client_deliverables"] = deliverables
            if check in ("all", "assignments"):
                results["assignment_gaps"] = check_assignment_gaps(deliverables)

        if check in ("all", "pm_tasks"):
            print("Checking PM tasks from Samu...", file=sys.stderr)
            results["pm_tasks"] = check_pm_tasks(args.hours)

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
