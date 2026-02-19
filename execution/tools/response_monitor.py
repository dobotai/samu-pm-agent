#!/usr/bin/env python3
"""
Response Monitor - Detect unanswered outbound messages to clients.

Monitors client channels for messages sent BY the PM/bot that haven't
received a client reply within a configurable threshold. Pings Simon
when client messages go unanswered.

Uses .tmp/notified_messages.json to avoid duplicate alerts.
Only operates during configured work hours (default 9:30-15:00 EST).

Actions:
    check_unanswered_outbound - Find client messages with no reply

Usage:
    python response_monitor.py check_unanswered_outbound '{"minutes_threshold": 30}'
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

CACHE_DIR = Path(__file__).parent.parent.parent / ".tmp"
NOTIFIED_FILE = CACHE_DIR / "notified_messages.json"


def _get_slack_client():
    token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
    if not token:
        return None
    return WebClient(token=token)


def _load_notified() -> set:
    """Load set of already-notified message timestamps."""
    if NOTIFIED_FILE.exists():
        try:
            data = json.loads(NOTIFIED_FILE.read_text())
            return set(data.get("notified_ts", []))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def _save_notified(notified: set):
    """Save notified message timestamps. Prune entries older than 24h."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now() - timedelta(hours=24)
    cutoff_ts = cutoff.timestamp()

    # Only keep recent entries
    pruned = [ts for ts in notified if float(ts) > cutoff_ts]
    NOTIFIED_FILE.write_text(json.dumps({"notified_ts": pruned}))


def _get_all_channels(slack_client):
    """Get all accessible channels."""
    try:
        channels = []
        cursor = None
        while True:
            kwargs = {"types": "public_channel,private_channel", "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            resp = slack_client.conversations_list(**kwargs)
            channels.extend(resp.get("channels", []))
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return channels
    except SlackApiError:
        return []


def _is_work_hours(start_hour: float = 9.5, end_hour: float = 15.0) -> bool:
    """Check if current time is within work hours."""
    now = datetime.now()
    current_hour = now.hour + now.minute / 60.0
    return start_hour <= current_hour <= end_hour


def check_unanswered_outbound(minutes_threshold: int = 30,
                               start_hour: float = 9.5,
                               end_hour: float = 15.0) -> dict:
    """Find outbound client messages with no reply within threshold.

    Scans client channels for messages sent by Simon (SIMON_SLACK_USER_ID)
    or the bot. If no client reply within minutes_threshold, flag it.
    """
    if not _is_work_hours(start_hour, end_hour):
        return {
            "success": True,
            "items": [],
            "count": 0,
            "note": "Outside work hours, skipping check",
        }

    slack = _get_slack_client()
    if not slack:
        return {"success": False, "error": "No Slack token configured"}

    simon_id = os.getenv("SIMON_SLACK_USER_ID", "")
    bot_user_id = os.getenv("SLACK_BOT_USER_ID", "")

    # Get all client channels
    all_channels = _get_all_channels(slack)
    client_channels = [
        ch for ch in all_channels
        # Channel convention: "{name}-client" (e.g. "adam-client", "taylor-client")
        if ch.get("name", "").lower().endswith("-client")
    ]

    notified = _load_notified()
    cutoff = datetime.now() - timedelta(minutes=minutes_threshold)
    cutoff_ts = cutoff.timestamp()

    # Only look back a few hours
    lookback = datetime.now() - timedelta(hours=4)
    lookback_ts = lookback.timestamp()

    items = []

    for ch in client_channels:
        channel_id = ch["id"]
        channel_name = ch.get("name", "")

        try:
            resp = slack.conversations_history(
                channel=channel_id, oldest=str(lookback_ts), limit=50
            )
            messages = resp.get("messages", [])
        except SlackApiError:
            continue

        if not messages:
            continue

        # Sort by timestamp ascending
        messages.sort(key=lambda m: float(m.get("ts", 0)))

        for i, msg in enumerate(messages):
            ts = msg.get("ts", "0")
            msg_ts = float(ts)
            user = msg.get("user", "")
            is_our_message = (user == simon_id or user == bot_user_id or msg.get("bot_id"))

            if not is_our_message:
                continue

            # Skip if already notified
            if ts in notified:
                continue

            # Skip if too recent
            if msg_ts > cutoff_ts:
                continue

            # Check if there's a reply after this message from someone else
            has_reply = False
            for j in range(i + 1, len(messages)):
                reply_user = messages[j].get("user", "")
                reply_bot = messages[j].get("bot_id")
                if reply_user != simon_id and reply_user != bot_user_id and not reply_bot:
                    has_reply = True
                    break

            if not has_reply:
                msg_time = datetime.fromtimestamp(msg_ts)
                minutes_ago = int((datetime.now() - msg_time).total_seconds() / 60)

                items.append({
                    "channel": channel_name,
                    "channel_id": channel_id,
                    "message_preview": msg.get("text", "")[:150],
                    "minutes_ago": minutes_ago,
                    "ts": ts,
                    "suggested_message": f"No client reply in #{channel_name} for {minutes_ago}min",
                })

                notified.add(ts)

    _save_notified(notified)

    # Build human-readable summary for DM
    if items:
        lines = [f"{len(items)} unanswered outbound message(s):"]
        for it in items:
            lines.append(f"- #{it['channel']}: no reply in {it['minutes_ago']}min")
        summary = "\n".join(lines)
    else:
        summary = "No unanswered outbound messages."

    return {
        "success": True,
        "items": items,
        "count": len(items),
        "summary": summary,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: response_monitor.py <action> '<json_params>'"}))
        sys.exit(1)

    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON params"}))
            sys.exit(1)

    if action == "check_unanswered_outbound":
        result = check_unanswered_outbound(
            minutes_threshold=params.get("minutes_threshold", 30),
            start_hour=params.get("start_hour", 9.5),
            end_hour=params.get("end_hour", 15.0),
        )
    else:
        result = {"error": f"Unknown action: {action}"}
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
