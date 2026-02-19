#!/usr/bin/env python3
"""
Payment Reminder - Send payment requests to editors on 15th and 30th.

Checks if today is the 15th or 30th of the month. If so, returns a list
of editors who need payment reminders with their channel info and
pre-composed messages.

Actions:
    check_and_remind - Check date and generate payment reminders if applicable

Usage:
    python payment_reminder.py check_and_remind '{}'
    python payment_reminder.py check_and_remind '{"force": true}'
"""

import json
import os
import sys
from datetime import datetime
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


PAYMENT_TEMPLATE = (
    "Hey, we're paying you today. Please send over how much $ we owe you "
    "and a breakdown of the videos you did. Thank you!"
)

INVOICE_FOLLOWUP = "Thanks. Could you send an invoice about it?"


def _get_airtable_records(table_name, filter_formula=None, fields=None):
    """Fetch Airtable records."""
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

    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        return [{"id": r["id"], "fields": r.get("fields", {})} for r in data.get("records", [])]
    except Exception:
        return []


def _get_slack_client():
    token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
    if not token:
        return None
    return WebClient(token=token)


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


def check_and_remind(force: bool = False) -> dict:
    """Check if today is payment day and return editor reminder list.

    Args:
        force: If True, generate reminders regardless of date (for testing).
    """
    today = datetime.now()
    is_payment_day = today.day in (15, 30) or (today.day == 28 and today.month == 2)

    if not is_payment_day and not force:
        return {
            "success": True,
            "items": [],
            "count": 0,
            "is_payment_day": False,
            "note": f"Today is the {today.day}th. Payment reminders only on 15th/30th.",
            "summary": f"Not a payment day (today is the {today.day}th).",
        }

    # Get editors from Team table
    records = _get_airtable_records(
        "Team",
        fields=["Name", "Role", "Status", "Slack ID Channel"]
    )

    # Filter to active editors
    editors = []
    for record in records:
        fields = record["fields"]
        name = fields.get("Name", "")
        role = str(fields.get("Role", "")).lower()
        status = str(fields.get("Status", "")).lower()
        channel_ids = fields.get("Slack ID Channel", [])

        # Include editors/freelancers who are active
        if not name:
            continue
        if "inactive" in status or "paused" in status:
            continue

        channel_id = channel_ids[0] if channel_ids else None

        editors.append({
            "name": name,
            "channel_id": channel_id,
            "message": PAYMENT_TEMPLATE,
        })

    # Try to match channels by name if no channel_id from Airtable
    slack = _get_slack_client()
    if slack:
        all_channels = _get_all_channels(slack)
        channel_map = {}
        for ch in all_channels:
            ch_name = ch.get("name", "").lower()
            if ch_name.endswith("-editing"):
                editor_part = ch_name[:-len("-editing")]
                channel_map[editor_part] = ch["id"]

        for editor in editors:
            if not editor["channel_id"]:
                name_lower = editor["name"].lower().split()[0]
                editor["channel_id"] = channel_map.get(name_lower)

    # Build human-readable summary for DM
    if editors:
        lines = [f"Payment day ({today.strftime('%b %d')})! {len(editors)} editor(s) to pay:"]
        for ed in editors:
            lines.append(f"- {ed['name']}")
        summary = "\n".join(lines)
    else:
        summary = "Payment day but no active editors found."

    return {
        "success": True,
        "items": editors,
        "count": len(editors),
        "is_payment_day": True,
        "date": today.strftime("%Y-%m-%d"),
        "summary": summary,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: payment_reminder.py <action> '<json_params>'"}))
        sys.exit(1)

    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON params"}))
            sys.exit(1)

    if action == "check_and_remind":
        result = check_and_remind(force=params.get("force", False))
    else:
        result = {"error": f"Unknown action: {action}"}
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
