#!/usr/bin/env python3
"""
Follow-up Monitor - Detect unanswered client follow-ups and editor questions.

Actions:
    check_client_followups  - Find videos sent to client with no reply in 24-48h
    check_editor_questions  - Find editor questions/problems not tended to

Usage:
    python followup_monitor.py check_client_followups '{"hours": 48}'
    python followup_monitor.py check_editor_questions '{"minutes_threshold": 30}'
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

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from utils import format_video_ref, get_client_map


def _get_slack_client():
    token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
    if not token:
        return None
    return WebClient(token=token)


def _get_airtable_records(table_name, filter_formula=None, fields=None):
    """Fetch Airtable records using raw HTTP (matches tools/ pattern)."""
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    if not api_key or not base_id:
        return []

    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"

    params = []
    if filter_formula:
        params.append(("filterByFormula", filter_formula))
    if fields:
        for f in fields:
            params.append(("fields[]", f))

    all_records = []
    offset = None

    while True:
        req_params = list(params)
        if offset:
            req_params.append(("offset", offset))

        try:
            resp = requests.get(url, headers=headers, params=req_params)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        for r in data.get("records", []):
            all_records.append({"id": r["id"], "fields": r.get("fields", {})})

        offset = data.get("offset")
        if not offset:
            break

    return all_records


def _get_channel_messages(slack_client, channel_id, since_hours=48):
    """Get recent messages from a Slack channel."""
    try:
        oldest = (datetime.now() - timedelta(hours=since_hours)).timestamp()
        resp = slack_client.conversations_history(
            channel=channel_id, oldest=str(oldest), limit=100
        )
        return resp.get("messages", [])
    except SlackApiError:
        return []


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


def check_client_followups(hours: int = 48) -> dict:
    """Find videos sent to client for review with no client reply.

    Checks Airtable for videos at status '75 - Sent for Review' and
    cross-references with Slack client channels for recent replies.
    """
    slack = _get_slack_client()
    if not slack:
        return {"success": False, "error": "No Slack token configured"}

    client_map = get_client_map()

    # Get videos in client review status
    records = _get_airtable_records(
        "Videos",
        filter_formula="{Editing Status} = '75 - Sent for Review'",
        fields=["Video ID", "Client", "Video Number", "Format", "Deadline",
                "Editing Status", "Assigned Editor", "Editor's Name"]
    )

    if not records:
        return {"success": True, "items": [], "count": 0}

    # Get all channels to find client channels
    all_channels = _get_all_channels(slack)
    client_channels = {}
    for ch in all_channels:
        name = ch.get("name", "").lower()
        # Channel convention: "{name}-client" (e.g. "adam-client", "taylor-client")
        if name.endswith("-client"):
            client_part = name[:-len("-client")]  # "adam-client" → "adam"
            client_channels[client_part] = ch["id"]

    items = []
    for record in records:
        fields = record["fields"]
        display_name = format_video_ref(fields, client_map)

        # Resolve client name
        client_ids = fields.get("Client", [])
        client_name = "Unknown"
        if client_ids and client_map:
            cid = client_ids[0] if isinstance(client_ids, list) else client_ids
            client_name = client_map.get(cid, "Unknown")

        # Find matching client channel
        channel_id = None
        for key, cid in client_channels.items():
            if client_name.lower().startswith(key) or key.startswith(client_name.lower()):
                channel_id = cid
                break

        if not channel_id:
            items.append({
                "name": display_name,
                "client": client_name,
                "channel": "not found",
                "hours_since": "unknown",
                "suggested_message": f"Follow up with {client_name} about {display_name} review status",
            })
            continue

        # Check for client replies in the channel
        messages = _get_channel_messages(slack, channel_id, hours)
        if not messages:
            items.append({
                "name": display_name,
                "client": client_name,
                "channel": channel_id,
                "hours_since": hours,
                "suggested_message": f"No messages in #{client_name} channel in {hours}h. Follow up on {display_name} review.",
            })

    return {"success": True, "items": items, "count": len(items)}


def check_editor_questions(minutes_threshold: int = 30) -> dict:
    """Find unanswered editor questions/problems.

    Scans editor channels for messages containing question marks or
    problem keywords that haven't received a reply within the threshold.
    """
    slack = _get_slack_client()
    if not slack:
        return {"success": False, "error": "No Slack token configured"}

    all_channels = _get_all_channels(slack)
    editor_channels = [
        ch for ch in all_channels
        # Channel convention: "{name}-editing" (e.g. "denis-editing", "josh-editing")
        if ch.get("name", "").lower().endswith("-editing")
    ]

    question_keywords = ["?", "help", "issue", "problem", "blocked", "stuck", "can't", "error"]
    cutoff = datetime.now() - timedelta(minutes=minutes_threshold)
    cutoff_ts = cutoff.timestamp()

    items = []
    for ch in editor_channels:
        channel_id = ch["id"]
        channel_name = ch.get("name", "")

        # Get recent messages (last 4 hours)
        messages = _get_channel_messages(slack, channel_id, since_hours=4)
        if not messages:
            continue

        for msg in messages:
            text = msg.get("text", "")
            ts = float(msg.get("ts", 0))
            user = msg.get("user", "")

            # Skip bot messages and old messages
            if msg.get("bot_id") or msg.get("subtype"):
                continue

            # Check if message is a question/problem
            text_lower = text.lower()
            is_question = any(kw in text_lower for kw in question_keywords)
            if not is_question:
                continue

            # Check if message is within the unanswered window
            msg_time = datetime.fromtimestamp(ts)
            if msg_time > cutoff:
                # Too recent to flag
                continue

            # Check if there's a reply (thread or subsequent message)
            has_reply = False
            reply_count = msg.get("reply_count", 0)
            if reply_count > 0:
                has_reply = True

            if not has_reply:
                items.append({
                    "channel": channel_name,
                    "channel_id": channel_id,
                    "user": user,
                    "message": text[:200],
                    "minutes_ago": int((datetime.now() - msg_time).total_seconds() / 60),
                    "suggested_message": f"Editor question in #{channel_name} unanswered for {int((datetime.now() - msg_time).total_seconds() / 60)}min",
                })

    # Build human-readable summary for DM
    if items:
        lines = [f"{len(items)} unanswered editor question(s):"]
        for it in items:
            lines.append(f"- #{it['channel']}: \"{it['message'][:80]}\" ({it['minutes_ago']}min ago)")
        summary = "\n".join(lines)
    else:
        summary = "No unanswered editor questions."

    return {"success": True, "items": items, "count": len(items), "summary": summary}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: followup_monitor.py <action> '<json_params>'"}))
        sys.exit(1)

    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON params"}))
            sys.exit(1)

    if action == "check_client_followups":
        result = check_client_followups(hours=params.get("hours", 48))
    elif action == "check_editor_questions":
        result = check_editor_questions(minutes_threshold=params.get("minutes_threshold", 30))
    else:
        result = {"error": f"Unknown action: {action}"}
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
