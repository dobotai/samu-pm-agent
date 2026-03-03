#!/usr/bin/env python3
"""
Client Status & Sentiment Report
Scans *-client Slack channels and cross-references Airtable video data.
Outputs markdown tables grouped by risk level.

Usage:
    python client_status_report.py [--hours 72] [--client Josh] [--output markdown|json]
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime, timedelta
from collections import defaultdict

# Shared helpers
sys.path.insert(0, os.path.dirname(__file__))
from airtable_read import read_airtable_records
from slack_read_channel import read_slack_channel
from slack_list_channels import list_slack_channels
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
from utils import get_client_map
from constants import (
    ALL_ACTIVE_STATUSES, INACTIVE_CLIENT_STATUSES,
    STATUS_SHORT, STATUS_ORDER, CLIENT_RESPONSE_SLOW_HOURS,
)


# ---------------------------------------------------------------------------
# Sentiment keywords & patterns
# ---------------------------------------------------------------------------

# Explicit praise — signals genuine satisfaction (required for "Happy" mood)
STRONGLY_POSITIVE_KEYWORDS = [
    'really happy', 'love it', 'love the', 'loving the', 'love how',
    'excellent', 'amazing', 'fantastic', 'brilliant', 'impressed',
    'blown away', 'outstanding', 'incredible', 'phenomenal',
    'really happy how', 'so happy with', 'exceeded expectations',
    'best video', 'best content', 'really pleased',
]

# Professional courtesy — does NOT count toward "Happy" mood
POSITIVE_KEYWORDS = [
    'great', 'awesome', 'perfect', 'love', 'excellent', 'amazing', 'fantastic',
    'thank', 'thanks', 'appreciate', 'happy', 'pleased', 'wonderful', 'brilliant',
    'good job', 'well done', 'nice', 'excited', 'impressive'
]

NEGATIVE_KEYWORDS = [
    'disappointed', 'frustrat', 'upset', 'unhappy', 'wrong', 'issue', 'problem',
    'concern', 'not happy', 'confused', 'unclear', 'mistake', 'error', 'redo',
    'urgent', 'asap', 'immediately', 'overdue',
    # Quality & expectation signals (from real channel data)
    'not what i', 'not what we', 'not ideal', 'not great', 'off brand',
    'missed', 'too long', 'haven\'t heard', 'no update',
]

# High-signal churn / pause / cancel keywords — auto-bump to High risk
CHURN_KEYWORDS = [
    # Direct cancellation
    'cancel', 'canceling', 'cancelling', 'cancellation',
    # Pause / hold (specific enough to be client-side signals)
    'hold off', 'put on hold', 'on hold', 'pausing the',
    # Stepping back (specific phrases)
    'taking a break', 'stepping back', 'not continu', 'not continuing',
    'won\'t be doing', 'won\'t be able to do the videos',
    # Capacity / availability signals (wave-connect pattern)
    'won\'t be able to do the video', 'not going to be able to do the video',
    'can\'t do the video', 'can\'t film', 'won\'t be filming',
    # Priority / engagement shift (dean-client pattern)
    'not a priority', 'no longer a priority', 'things came up',
    'got slammed', 'no longer need',
    # Going elsewhere
    'doing it ourselves', 'in-house', 'found someone else', 'going with another',
    # Budget / ROI
    'too expensive', 'can\'t afford', 'budget cut', 'cutting budget',
    'not seeing results', 'not working for us',
]

QUESTION_PATTERNS = [
    r'\?$', r'when will', r'where is', r'what about', r'any update',
    r'status', r'eta', r'how long', r'can you'
]

ACKNOWLEDGMENT_PATTERNS = [
    r'^(ok|okay|k|kk)[\.\!]?$',
    r'^(thanks|thank you|thx|ty)[\.\!]?$',
    r'^(awesome|great|perfect|nice|cool|sounds good|got it|noted)[\.\!]?$',
    r'^(yes|yep|yup|yeah|yea)[\.\!]?$',
    r'^(no problem|np|no worries|nw)[\.\!]?$',
    r'^\:[\w\+\-]+\:$',
    r'^(will do|on it|doing it now)[\.\!]?$',
]


# ---------------------------------------------------------------------------
# Message classification helpers
# ---------------------------------------------------------------------------

def _is_delivery_message(text):
    """Detect team delivery notifications by content (links + delivery/schedule phrases)."""
    text_lower = text.lower()

    # Delivery phrases
    has_delivery_phrase = any(p in text_lower for p in [
        'ready for review', 'ready for checking', 'ready to check',
        'ready for your review',
        'is scheduled', 'scheduled to go live', 'going live',
        'video is ready', 'here is the video', 'here\'s the video',
    ])

    # Video links (Frame.io, Google Drive, YouTube)
    has_link = any(link in text_lower for link in [
        'f.io/', 'frame.io', 'drive.google', 'youtu.be', 'youtube.com'
    ])

    return has_delivery_phrase and has_link


def is_acknowledgment(text):
    """Check if message is just an acknowledgment that doesn't need response."""
    text_lower = text.lower().strip()
    if len(text_lower) < 15:
        for pattern in ACKNOWLEDGMENT_PATTERNS:
            if re.match(pattern, text_lower, re.IGNORECASE):
                return True
    return False


def needs_response(text):
    """Check if a message actually needs a response."""
    if is_acknowledgment(text):
        return False

    text_lower = text.lower()

    if '?' in text:
        return True

    request_patterns = [
        r'can you', r'could you', r'please', r'need', r'want',
        r'when will', r'where is', r'what about', r'any update',
        r'let me know', r'waiting for', r'status on'
    ]
    for pattern in request_patterns:
        if pattern in text_lower:
            return True

    if len(text) > 100:
        return True

    return False


def analyze_sentiment(text):
    """Analyze sentiment of a message.

    Returns (category, score) where category is one of:
        'strongly_positive' — explicit praise (e.g. "really happy with the results")
        'positive' — mild professional courtesy (e.g. "thanks", "great")
        'negative', 'questioning', 'neutral'
    """
    text_lower = text.lower()

    strongly_positive = sum(1 for kw in STRONGLY_POSITIVE_KEYWORDS if kw in text_lower)
    positive_score = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    negative_score = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)
    has_question = any(re.search(p, text_lower) for p in QUESTION_PATTERNS)

    if negative_score > positive_score:
        return 'negative', negative_score
    elif strongly_positive > 0:
        return 'strongly_positive', strongly_positive
    elif positive_score > negative_score:
        return 'positive', positive_score
    elif has_question:
        return 'questioning', 1
    else:
        return 'neutral', 0


def detect_churn_signals(messages, team_slack_ids):
    """Check CLIENT messages for churn/pause/cancel keywords.

    Only scans messages from non-team members (clients) to avoid false positives
    from KS Media team saying things like "wrapping up the thumbnail".

    Returns list of {keyword, text, user, hours_ago} for any matches found.
    Churn signals auto-bump a client to High risk regardless of other factors.
    """
    signals = []
    now = datetime.now()
    for msg in messages:
        # Skip team messages — KS Media team says "wrapping up", "pause" etc constantly
        user_id = msg.get("user_id", "unknown")
        if user_id == "unknown" or user_id in team_slack_ids:
            continue

        text = msg.get("text", "")
        if not text:
            continue
        text_lower = text.lower()
        for kw in CHURN_KEYWORDS:
            if kw in text_lower:
                ts = float(msg.get("timestamp", "0"))
                msg_time = datetime.fromtimestamp(ts)
                hours_ago = (now - msg_time).total_seconds() / 3600
                signals.append({
                    "keyword": kw,
                    "text": text[:120],
                    "user": msg.get("user", "Unknown"),
                    "hours_ago": round(hours_ago, 1),
                })
                break  # one signal per message is enough
    return signals



# Slack reactions that signal positive client sentiment
APPROVAL_REACTIONS = {
    "+1", "thumbsup", "white_check_mark", "heavy_check_mark",
    "heart", "fire", "100", "tada", "raised_hands", "clap",
    "ok_hand", "star", "star2", "rocket",
}


def check_approval_reactions(messages, team_slack_ids):
    """Count client approval reactions on team messages.

    Returns the number of distinct messages where a client reacted
    with an approval emoji. A single reaction could just be an
    acknowledgment — require 2+ to signal genuine satisfaction.
    """
    count = 0
    for msg in messages:
        reactions = msg.get("reactions", [])
        if not reactions:
            continue
        # Only care about reactions on team messages (client reacting to our work)
        msg_user = msg.get("user_id", "")
        if msg_user not in team_slack_ids:
            continue
        for reaction in reactions:
            name = reaction.get("name", "")
            if name not in APPROVAL_REACTIONS:
                continue
            # Check if any reactor is NOT a team member (i.e. a client)
            reactors = reaction.get("users", [])
            if any(uid not in team_slack_ids for uid in reactors):
                count += 1
                break  # One approval per message is enough, move to next msg
    return count



# ---------------------------------------------------------------------------
# Data fetchers (using shared helpers)
# ---------------------------------------------------------------------------

def get_team_slack_ids():
    """Get team member Slack IDs from Airtable Team table."""
    try:
        team = read_airtable_records("Team", fields=["Name", "Slack ID"])
        ids = set()
        for r in team:
            sid = r["fields"].get("Slack ID", "")
            if sid:
                ids.add(sid)
        # Add key people who may not be in Team table
        ids.add("U070CUSP75M")  # Samu
        ids.add("U09SVR0R2GH")  # Simon (PM/ops manager)
        return ids
    except Exception:
        return set()


def get_client_video_stats():
    """Get active video counts per client from Airtable.

    Returns:
        stats: {client_name: {"active_count": int, "status_counts": {status: count}}}
        current_client_names: set of current/onboarding client names
        onboarding_names: set of onboarding client names
        inactive_client_names: set of inactive/paused client names (for filtering)
    """
    # Get all clients with status
    clients = read_airtable_records("Clients", fields=["Name", "Status"])
    current_clients = {}
    onboarding_names = set()
    inactive_client_names = set()
    for c in clients:
        status = c["fields"].get("Status", "")
        name = c["fields"].get("Name", "Unknown")
        if status in ("Current", "Onboarding"):
            current_clients[c["id"]] = name
            if status == "Onboarding":
                onboarding_names.add(name)
        elif status in INACTIVE_CLIENT_STATUSES:
            inactive_client_names.add(name)

    # Get active videos (not completed) — use canonical status names
    formula_parts = [f"{{Editing Status}}='{s}'" for s in ALL_ACTIVE_STATUSES]
    formula = f"OR({', '.join(formula_parts)})"

    videos = read_airtable_records(
        "Videos",
        filter_formula=formula,
        fields=["Client", "Video Number", "Format", "Editing Status"],
    )

    stats = defaultdict(lambda: {"active_count": 0, "status_counts": defaultdict(int)})

    for v in videos:
        f = v["fields"]
        client_ids = f.get("Client", [])
        if not client_ids:
            continue
        cid = client_ids[0] if isinstance(client_ids, list) else client_ids

        if cid not in current_clients:
            continue

        client_name = current_clients[cid]
        status = f.get("Editing Status", "")

        stats[client_name]["active_count"] += 1
        stats[client_name]["status_counts"][status] += 1

    return dict(stats), set(current_clients.values()), onboarding_names, inactive_client_names


def get_days_since_delivery():
    """Get days since the most recent completed video per client.

    Returns: {client_name: days_since_int} for clients with at least one delivery.
    """
    try:
        records = read_airtable_records(
            "Videos",
            filter_formula="{Editing Status}='100 - Scheduled - DONE'",
            fields=["Client", "Last Modified (Editing Status)"],
        )
    except Exception:
        return {}

    # Get client map for name resolution
    try:
        from tools.utils import get_client_map as _get_client_map
        client_map = _get_client_map()
    except Exception:
        client_map = {}

    # Find most recent delivery per client
    latest = {}  # {client_name: datetime}
    for r in records:
        fields = r["fields"]
        client_ids = fields.get("Client", [])
        if not client_ids:
            continue
        cid = client_ids[0] if isinstance(client_ids, list) else client_ids
        client_name = client_map.get(cid, "")
        if not client_name:
            continue

        lm = fields.get("Last Modified (Editing Status)", "")
        if not lm:
            continue
        try:
            dt = datetime.fromisoformat(lm.replace("Z", "+00:00"))
            if client_name not in latest or dt > latest[client_name]:
                latest[client_name] = dt
        except (ValueError, TypeError):
            continue

    now = datetime.now().astimezone()
    result = {}
    for name, dt in latest.items():
        days = (now - dt).days
        result[name] = days
    return result


# ---------------------------------------------------------------------------
# Response time analysis (adapted for read_slack_channel message format)
# ---------------------------------------------------------------------------

def _business_hours_between(start, end):
    """Count business hours (Mon-Fri 9am-6pm) between two datetimes.

    Messages sent outside business hours are "free" — the clock doesn't
    start until the next business-hours window opens.
    """
    BIZ_START = 9   # 9am
    BIZ_END = 18    # 6pm
    HOURS_PER_DAY = BIZ_END - BIZ_START  # 9 hours

    if end <= start:
        return 0.0

    total = 0.0
    current = start

    # Cap at 7 days to avoid runaway loops
    max_end = start + timedelta(days=7)
    if end > max_end:
        end = max_end

    while current < end:
        # Skip weekends
        if current.weekday() >= 5:  # Saturday=5, Sunday=6
            # Jump to Monday 9am
            days_until_monday = 7 - current.weekday()
            current = current.replace(hour=BIZ_START, minute=0, second=0) + timedelta(days=days_until_monday)
            continue

        # Clamp to business hours
        day_start = current.replace(hour=BIZ_START, minute=0, second=0)
        day_end = current.replace(hour=BIZ_END, minute=0, second=0)

        # If we're before business hours, jump to start
        if current < day_start:
            current = day_start
            continue

        # If we're after business hours, jump to next day
        if current >= day_end:
            current = (current + timedelta(days=1)).replace(hour=BIZ_START, minute=0, second=0)
            continue

        # We're within business hours — count until end of day or end time
        window_end = min(day_end, end)
        total += (window_end - current).total_seconds() / 3600
        current = window_end

    return round(total, 2)


def calculate_response_times(messages, team_slack_ids):
    """Calculate average response time to client messages.

    Uses business hours (Mon-Fri 9am-6pm) so overnight/weekend gaps
    don't inflate response times.

    read_slack_channel message format:
        msg['user_id']   — raw Slack user ID (for team member check)
        msg['timestamp'] — raw ts string
        msg['text']      — message text
        msg['user']      — resolved display name
    """
    if not messages:
        return None, []

    # Flatten thread replies into the message stream for response time calculation
    expanded = []
    for msg in messages:
        expanded.append(msg)
        for reply in msg.get("thread_replies", []):
            expanded.append(reply)
    sorted_msgs = sorted(expanded, key=lambda m: float(m.get("timestamp", "0")))

    response_times = []
    unanswered = []

    pending_client_msg = None
    pending_client_time = None
    pending_client_user = None

    for msg in sorted_msgs:
        user_id = msg.get("user_id", "unknown")
        text = msg.get("text", "")

        if user_id == "unknown":
            continue

        ts = float(msg.get("timestamp", "0"))
        msg_time = datetime.fromtimestamp(ts)

        is_team = user_id in team_slack_ids

        if is_team:
            if pending_client_msg and pending_client_time:
                response_time = _business_hours_between(pending_client_time, msg_time)
                if response_time < 48:
                    response_times.append(response_time)
                pending_client_msg = None
                pending_client_time = None
                pending_client_user = None
        else:
            if needs_response(text):
                pending_client_msg = msg
                pending_client_time = msg_time
                pending_client_user = msg.get("user", "Unknown")

    # Check for trailing unanswered message (use real hours for "unanswered" urgency)
    # A team reaction (emoji) on the client message counts as acknowledgment
    if pending_client_msg and pending_client_time:
        team_reacted = False
        for reaction in pending_client_msg.get("reactions", []):
            reactors = set(reaction.get("users", []))
            if reactors & team_slack_ids:
                team_reacted = True
                break
        if not team_reacted:
            hours_ago = (datetime.now() - pending_client_time).total_seconds() / 3600
            if hours_ago > 4:
                unanswered.append({
                    "text": pending_client_msg.get("text", "")[:100],
                    "user": pending_client_user,
                    "hours_ago": round(hours_ago, 1),
                    "timestamp": pending_client_time.strftime("%Y-%m-%d %H:%M"),
                })

    avg_response = sum(response_times) / len(response_times) if response_times else None
    return avg_response, unanswered


# ---------------------------------------------------------------------------
# Pipeline & last-contact helpers
# ---------------------------------------------------------------------------

def format_pipeline(vs):
    """Format video stats as compact pipeline string. e.g. '4 (2 QC, 1 editing, 1 client rev)'"""
    count = vs.get("active_count", 0)
    if count == 0:
        return "0"
    status_counts = vs.get("status_counts", {})
    if not status_counts:
        return str(count)
    parts = []
    for status in sorted(status_counts.keys(), key=lambda s: STATUS_ORDER.get(s, 999)):
        cnt = status_counts[status]
        prefix = status.split(" - ")[0].strip() if " - " in status else ""
        short = STATUS_SHORT.get(prefix, status.split(" - ", 1)[-1][:8] if " - " in status else status[:8])
        parts.append(f"{cnt} {short}")
    return f"{count} ({', '.join(parts)})"


def get_last_contact(messages, team_slack_ids):
    """Determine who sent the last meaningful message and when.

    Returns: {"direction": "ours"|"theirs", "hours_ago": float, "user": str} or None
      - "ours"  = client messaged last → ball is in OUR court (we need to respond)
      - "theirs" = team messaged last → ball is in THEIR court (waiting on client)
    """
    if not messages:
        return None
    # messages from read_slack_channel are newest-first
    for msg in messages:
        user_id = msg.get("user_id", "unknown")
        text = msg.get("text", "")
        if user_id == "unknown" or not text or len(text) < 3:
            continue
        if is_acknowledgment(text):
            continue
        ts = float(msg.get("timestamp", "0"))
        hours_ago = (datetime.now() - datetime.fromtimestamp(ts)).total_seconds() / 3600
        is_team = user_id in team_slack_ids
        return {
            "direction": "theirs" if is_team else "ours",
            "hours_ago": round(hours_ago, 1),
            "user": msg.get("user", "Unknown"),
        }
    return None


def _format_ball(last_contact, scan_hours=72):
    """Format last-contact as actionable 'ball in court' string."""
    if not last_contact:
        return "—"
    h = last_contact["hours_ago"]
    # Sanity check: flag unreasonably old data (beyond 3x scan window)
    suspect = h > scan_hours * 3
    if h < 24:
        time_str = f"{int(h)}h ago"
    else:
        days = h / 24
        time_str = f"{int(days)}d ago" if days >= 2 else f"{round(days, 1)}d ago"
    if suspect:
        time_str += " (verify)"
    if last_contact["direction"] == "ours":
        return f"Reply ({time_str})"
    else:
        return f"Waiting ({time_str})"


# ---------------------------------------------------------------------------
# Report generation (Phase 1 / 2 / 3)
# ---------------------------------------------------------------------------

def generate_client_report(hours=72, target_client=None):
    """Generate client status reports.

    Phase 1: Airtable (video stats, team IDs)
    Phase 2: Slack scanning (sentiment, response times)
    Phase 3: Assembly (quiet clients, sort)
    """
    # --- Phase 1: Airtable ---
    print("Phase 1: Fetching Airtable data...", file=sys.stderr)
    video_stats, current_client_names, onboarding_names, inactive_client_names = get_client_video_stats()
    team_slack_ids = get_team_slack_ids()
    delivery_days = get_days_since_delivery()
    print(f"  {len(video_stats)} clients with active videos, {len(team_slack_ids)} team members", file=sys.stderr)

    # --- Phase 2: Slack scanning ---
    print("Phase 2: Scanning Slack channels...", file=sys.stderr)
    channels = list_slack_channels(filter_pattern="-client")
    channels = [ch for ch in channels if not ch.get("is_archived", False)]
    print(f"  Found {len(channels)} client channels", file=sys.stderr)

    reports = []
    scanned_clients = set()
    for channel in channels:
        channel_name = channel["name"]
        channel_id = channel["id"]

        # "josh-client" → "Josh"
        client_name_from_channel = channel_name.replace("-client", "").replace("-", " ").title()

        # Match to Airtable client name (exact first, then fuzzy)
        matched_client = None
        all_airtable_names = list(video_stats.keys()) + list(current_client_names)
        # Pass 1: exact match (case-insensitive)
        for airtable_name in all_airtable_names:
            if airtable_name.lower() == client_name_from_channel.lower():
                matched_client = airtable_name
                break
        # Pass 2: word-prefix match — one name starts the other as a whole word
        # "Sam" matches "Sam Channel", "Fibbler" matches "Fibbler Adam",
        # but "Dan" does NOT match "Jordan" or "Daniel"
        if not matched_client:
            for airtable_name in all_airtable_names:
                a, c = airtable_name.lower(), client_name_from_channel.lower()
                if c.startswith(a + " ") or a.startswith(c + " "):
                    matched_client = airtable_name
                    break

        display_name = matched_client or client_name_from_channel

        # Skip inactive/paused clients (e.g., KD)
        if display_name in inactive_client_names:
            continue
        # Also check channel-derived name against inactive list (fuzzy)
        if any(display_name.lower() == iname.lower() for iname in inactive_client_names):
            continue

        if target_client:
            if target_client.lower() not in display_name.lower():
                continue

        scanned_clients.add(display_name)

        # Read messages with threads — client feedback often happens in thread replies
        try:
            messages = read_slack_channel(channel_id, limit=200, since_hours=hours, include_threads=True, max_threads=30)
        except Exception:
            messages = []

        if not messages:
            vs = video_stats.get(display_name, {})
            if vs.get("active_count", 0) > 0:
                reports.append({
                    "client_name": display_name,
                    "channel": channel_name,
                    "message_count": 0,
                    "overall_mood": "Quiet",
                    "risk_level": "Low",
                    "risk_factors": [],
                    "avg_response_time_hours": None,
                    "unanswered_messages": [],
                    "active_videos": vs.get("active_count", 0),
                    "pipeline": format_pipeline(vs),
                    "last_contact": None,
                    "is_onboarding": display_name in onboarding_names,
                    "recent_context": [],
                })
            continue

        # Sentiment (include thread replies — client feedback often lives in threads)
        sentiment_scores = {"positive": 0, "negative": 0, "neutral": 0, "questioning": 0, "strongly_positive": 0}
        for msg in messages:
            for text_source in [msg] + msg.get("thread_replies", []):
                text = text_source.get("text", "")
                if not text or len(text) < 5:
                    continue
                sentiment, _score = analyze_sentiment(text)
                sentiment_scores[sentiment] += 1

        # Response times
        avg_response, unanswered = calculate_response_times(messages, team_slack_ids)

        # Churn signal detection (client messages only)
        churn_signals = detect_churn_signals(messages, team_slack_ids)

        # Last contact direction (ball in court)
        last_contact = get_last_contact(messages, team_slack_ids)

        # Approval reactions (client thumbs-up on deliveries, etc.)
        # 2+ approval reactions = genuine satisfaction, 1 could just be acknowledging
        approval_reaction_count = check_approval_reactions(messages, team_slack_ids)

        # Overall mood
        # "Happy" requires explicit praise (strongly_positive), not just "thanks"
        total_sentiment = sum(sentiment_scores.values())
        if total_sentiment > 0:
            neg_ratio = sentiment_scores["negative"] / total_sentiment
            question_ratio = sentiment_scores.get("questioning", 0) / total_sentiment
            has_strong_positive = sentiment_scores.get("strongly_positive", 0) > 0

            if churn_signals:
                overall_mood = "Churn Risk"
            elif neg_ratio > 0.3:
                overall_mood = "Concerned"
            elif has_strong_positive or approval_reaction_count >= 2:
                overall_mood = "Happy"
            elif question_ratio > 0.3:
                overall_mood = "Seeking Updates"
            else:
                overall_mood = "Neutral"
        else:
            overall_mood = "Quiet"

        # Risk assessment
        risk_factors = []
        if churn_signals:
            matched_kws = list({s["keyword"] for s in churn_signals})[:2]
            risk_factors.append(f"CHURN SIGNAL: \"{', '.join(matched_kws)}\"")
        if unanswered:
            # Show preview of first unanswered message
            first_msg = unanswered[0]["text"][:60]
            if len(unanswered) == 1:
                risk_factors.append(f"Unanswered: \"{first_msg}\"")
            else:
                risk_factors.append(f"{len(unanswered)} unanswered: \"{first_msg}\"")
        if avg_response and avg_response > CLIENT_RESPONSE_SLOW_HOURS:
            risk_factors.append(f"Slow response ({round(avg_response, 1)}h avg)")

        # Churn signals auto-bump to High regardless of other factors
        if churn_signals:
            risk_level = "High"
        else:
            risk_level = "High" if len(risk_factors) >= 2 else ("Medium" if risk_factors else "Low")

        vs = video_stats.get(display_name, {})

        # Extract last 2-3 client messages as raw context (including thread replies)
        all_msgs_flat = []
        for m in messages:
            all_msgs_flat.append(m)
            for reply in m.get("thread_replies", []):
                all_msgs_flat.append(reply)
        client_msgs = [
            m for m in all_msgs_flat
            if m.get("user_id", "") not in team_slack_ids
            and m.get("user", "").lower() != "airtable"
            and m.get("username", "") != "airtable2"
            and len(m.get("text", "")) > 10
        ]
        client_msgs.sort(key=lambda m: float(m.get("timestamp", 0)), reverse=True)

        recent_context = []
        for cm in client_msgs[:3]:
            ts = float(cm.get("timestamp", 0))
            hours_ago = (datetime.now() - datetime.fromtimestamp(ts)).total_seconds() / 3600
            text = cm.get("text", "").strip()[:150]
            text = re.sub(r"\n+", " | ", text)
            recent_context.append({"text": text, "hours_ago": round(hours_ago, 1)})

        reports.append({
            "client_name": display_name,
            "channel": channel_name,
            "message_count": len(messages),
            "overall_mood": overall_mood,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "avg_response_time_hours": round(avg_response, 1) if avg_response else None,
            "unanswered_messages": unanswered[:3],
            "churn_signals": churn_signals[:3],
            "active_videos": vs.get("active_count", 0),
            "pipeline": format_pipeline(vs),
            "last_contact": last_contact,
            "is_onboarding": display_name in onboarding_names,
            "days_since_delivery": delivery_days.get(display_name),
            "recent_context": recent_context,
        })

    # --- Phase 3: Add quiet clients (Airtable but no Slack channel scanned) ---
    for client_name in current_client_names:
        if client_name not in scanned_clients and \
           video_stats.get(client_name, {}).get("active_count", 0) > 0:
            if target_client and target_client.lower() not in client_name.lower():
                continue
            reports.append({
                "client_name": client_name,
                "channel": None,
                "message_count": 0,
                "overall_mood": "Quiet",
                "risk_level": "Low",
                "risk_factors": [],
                "avg_response_time_hours": None,
                "unanswered_messages": [],
                "active_videos": video_stats[client_name].get("active_count", 0),
                "pipeline": format_pipeline(video_stats.get(client_name, {})),
                "last_contact": None,
                "is_onboarding": client_name in onboarding_names,
                "recent_context": [],
            })

    # Deduplicate by client name (multiple channels can map to the same client).
    # Keep the entry with the most messages (most representative).
    seen = {}
    for r in reports:
        name = r["client_name"]
        if name not in seen or r["message_count"] > seen[name]["message_count"]:
            seen[name] = r
    reports = list(seen.values())

    # Sort: High → Medium → Low, then message_count desc
    risk_order = {"High": 0, "Medium": 1, "Low": 2}
    reports.sort(key=lambda r: (risk_order.get(r["risk_level"], 3), -r["message_count"]))

    return reports


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def format_markdown_report(reports, hours):
    """Format reports as markdown tables grouped by risk level."""
    lines = []
    lines.append(f"## Client Status Report ({hours}h scan)")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    high = [r for r in reports if r["risk_level"] == "High"]
    medium = [r for r in reports if r["risk_level"] == "Medium"]
    low = [r for r in reports if r["risk_level"] == "Low" and r["message_count"] > 0]
    quiet = [r for r in reports if r["message_count"] == 0]

    if high:
        lines.append(f"### NEEDS ATTENTION — High Risk ({len(high)})")
        lines.append("")
        lines.append("| # | Client | Mood | Risk Factors | Pipeline | Ball | Unanswered |")
        lines.append("|---|--------|------|-------------|----------|------|------------|")
        for i, r in enumerate(high, 1):
            risk_str = "; ".join(r["risk_factors"]) if r["risk_factors"] else "—"
            unanswered_count = len(r["unanswered_messages"])
            name = f"[NEW] {r['client_name']}" if r.get("is_onboarding") else r["client_name"]
            ball = _format_ball(r.get("last_contact"))
            lines.append(f"| {i} | {name} | {r['overall_mood']} | {risk_str} | {r['pipeline']} | {ball} | {unanswered_count} |")

        for r in high:
            if r.get("churn_signals"):
                lines.append("")
                lines.append(f"**{r['client_name']}** churn signals:")
                for cs in r["churn_signals"]:
                    lines.append(f"- [{cs['hours_ago']}h ago] {cs['user']}: \"{cs['text']}\"")
            if r["unanswered_messages"]:
                lines.append("")
                lines.append(f"**{r['client_name']}** unanswered:")
                for um in r["unanswered_messages"]:
                    lines.append(f"- [{um['hours_ago']}h ago] \"{um['text']}\"")
        lines.append("")

    if medium:
        lines.append(f"### MONITOR — Medium Risk ({len(medium)})")
        lines.append("")
        lines.append("| # | Client | Mood | Risk Factors | Pipeline | Ball | Last Delivery |")
        lines.append("|---|--------|------|-------------|----------|------|---------------|")
        for i, r in enumerate(medium, 1):
            risk_str = "; ".join(r["risk_factors"]) if r["risk_factors"] else "—"
            name = f"[NEW] {r['client_name']}" if r.get("is_onboarding") else r["client_name"]
            ball = _format_ball(r.get("last_contact"))
            dsd = r.get("days_since_delivery")
            delivery_str = f"{dsd}d ago" if dsd is not None else "—"
            lines.append(f"| {i} | {name} | {r['overall_mood']} | {risk_str} | {r['pipeline']} | {ball} | {delivery_str} |")
        lines.append("")

    if low:
        lines.append(f"### HEALTHY — Low Risk ({len(low)})")
        lines.append("")
        lines.append("| # | Client | Mood | Pipeline | Ball | Last Delivery |")
        lines.append("|---|--------|------|----------|------|---------------|")
        for i, r in enumerate(low, 1):
            name = f"[NEW] {r['client_name']}" if r.get("is_onboarding") else r["client_name"]
            ball = _format_ball(r.get("last_contact"))
            dsd = r.get("days_since_delivery")
            delivery_str = f"{dsd}d ago" if dsd is not None else "—"
            lines.append(f"| {i} | {name} | {r['overall_mood']} | {r['pipeline']} | {ball} | {delivery_str} |")
        lines.append("")

    if quiet:
        lines.append(f"### QUIET — No Messages ({len(quiet)})")
        lines.append("")
        lines.append("| # | Client | Pipeline |")
        lines.append("|---|--------|----------|")
        for i, r in enumerate(quiet, 1):
            name = f"[NEW] {r['client_name']}" if r.get("is_onboarding") else r["client_name"]
            lines.append(f"| {i} | {name} | {r['pipeline']} |")
        lines.append("")

    # CLIENT CONTEXT — Raw recent messages for LLM interpretation
    context_clients = [r for r in reports if r.get("recent_context")]
    if context_clients:
        lines.append("### CLIENT CONTEXT — Recent Messages")
        lines.append("")
        for r in context_clients:
            # Build label: "Wave Connect (Healthy)" or "Dan (Medium — Slow response)"
            mood = r["overall_mood"]
            risk = r["risk_level"]
            if risk == "High":
                label = f"**{r['client_name']}** (High Risk — {mood})"
            elif risk == "Medium":
                risk_detail = r["risk_factors"][0] if r["risk_factors"] else mood
                label = f"**{r['client_name']}** (Medium — {risk_detail})"
            else:
                label = f"**{r['client_name']}** ({mood})"
            lines.append(label + ":")
            for ctx in r["recent_context"]:
                h = ctx["hours_ago"]
                if h < 24:
                    time_str = f"{int(h)}h ago"
                else:
                    days = h / 24
                    time_str = f"{int(days)}d ago" if days >= 2 else f"{round(days, 1)}d ago"
                lines.append(f"- [{time_str}] \"{ctx['text']}\"")
            lines.append("")

    # Summary footer
    total = len(reports)
    attention = len(high) + len(medium)
    lines.append("---")
    lines.append(f"**{total} clients analyzed.{f' {attention} need attention.' if attention else ' All healthy.'}**")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Client status and sentiment report")
    parser.add_argument("--hours", type=int, default=72, help="Hours to look back (default: 72)")
    parser.add_argument("--client", type=str, default=None, help="Filter to specific client")
    parser.add_argument("--output", choices=["json", "markdown"], default="markdown", help="Output format")

    args = parser.parse_args()

    try:
        reports = generate_client_report(hours=args.hours, target_client=args.client)

        if args.output == "json":
            print(json.dumps(reports, indent=2))
        else:
            if not reports:
                print("No client activity found.")
                return 0
            print(format_markdown_report(reports, args.hours))

        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
