#!/usr/bin/env python3
"""
Day Rating - End-of-day PM quality score using Simon's A-F scale.

Grades the PM's day based on deterministic metrics (no LLM needed).
Only measures things within PM's control — client delays don't count.

Rating Scale (from Simon, approved by Samu):
    EXCELLENT (A): All critical tasks completed, no missed deadlines,
                   proactive communication, following up on upcoming deadlines
    GOOD (B):      1 minor task missed, core deliverables done, minor gaps
    FAIR (C):      2 tasks missed OR 1 medium-priority, some communication gaps
    POOR (D):      3+ tasks missed OR 1 critical, significant breakdown
    CRITICAL (F):  Multiple critical missed, major deadline missed,
                   client escalation required

Actions:
    rate_day - Generate end-of-day rating

Usage:
    python day_rating.py rate_day '{}'
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


def _get_slack_client():
    token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
    if not token:
        return None
    return WebClient(token=token)


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


def _get_all_channels(slack_client):
    """Get all channels."""
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


def _count_unanswered(slack_client, channels, prefix, hours=10):
    """Count unanswered messages in channels with given prefix."""
    target_channels = [c for c in channels if c.get("name", "").lower().startswith(prefix)]
    oldest = (datetime.now() - timedelta(hours=hours)).timestamp()
    unanswered = 0

    simon_id = os.getenv("SIMON_SLACK_USER_ID", "")

    for ch in target_channels:
        try:
            resp = slack_client.conversations_history(
                channel=ch["id"], oldest=str(oldest), limit=50
            )
            messages = resp.get("messages", [])
        except SlackApiError:
            continue

        for msg in messages:
            user = msg.get("user", "")
            if user == simon_id or msg.get("bot_id") or msg.get("subtype"):
                continue
            # Check if question or request
            text = msg.get("text", "").lower()
            if "?" in text or any(kw in text for kw in ["help", "need", "please", "can you"]):
                reply_count = msg.get("reply_count", 0)
                if reply_count == 0:
                    unanswered += 1

    return unanswered


def rate_day() -> dict:
    """Generate PM day rating based on deterministic metrics.

    Scoring breakdown:
    - Task completion rate (40%): Overdue tasks / total active tasks
    - Client message responsiveness (20%): Unanswered client messages
    - Editor message responsiveness (20%): Unanswered editor messages
    - Proactive deadline follow-ups (10%): Videos near deadline with recent activity
    - Overall unfollowed messages (10%): Total unanswered across all channels
    """
    today = datetime.now().date()

    # Metric 1: Task completion (40%)
    # Check overdue videos vs total active
    all_active = _get_airtable_records(
        "Videos",
        filter_formula="AND({Editing Status} != '100 - Scheduled - DONE', {Deadline} != '')",
        fields=["Editing Status", "Deadline"]
    )

    overdue_count = 0
    total_active = len(all_active)
    for r in all_active:
        deadline_str = r["fields"].get("Deadline", "")
        if deadline_str:
            try:
                deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
                if deadline < today:
                    overdue_count += 1
            except ValueError:
                pass

    if total_active > 0:
        task_score = max(0, 100 - (overdue_count / total_active * 100))
    else:
        task_score = 100

    # Metric 2 & 3: Message responsiveness (20% each)
    slack = _get_slack_client()
    client_unanswered = 0
    editor_unanswered = 0

    if slack:
        channels = _get_all_channels(slack)
        client_unanswered = _count_unanswered(slack, channels, "client", hours=10)
        editor_unanswered = _count_unanswered(slack, channels, "editor", hours=10)

    client_score = max(0, 100 - (client_unanswered * 25))  # -25 per unanswered
    editor_score = max(0, 100 - (editor_unanswered * 25))

    # Metric 4: Proactive deadline follow-ups (10%)
    # Videos due in 1-2 days — ideally PM has checked on these
    upcoming = _get_airtable_records(
        "Videos",
        filter_formula="AND({Editing Status} != '100 - Scheduled - DONE', {Deadline} != '')",
        fields=["Deadline"]
    )
    upcoming_count = 0
    for r in upcoming:
        deadline_str = r["fields"].get("Deadline", "")
        if deadline_str:
            try:
                deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
                days_until = (deadline - today).days
                if 0 <= days_until <= 2:
                    upcoming_count += 1
            except ValueError:
                pass

    # If there are upcoming deadlines, score based on whether overdue count is low
    if upcoming_count > 0:
        proactive_score = max(0, 100 - (overdue_count * 20))
    else:
        proactive_score = 100

    # Metric 5: Overall unfollowed (10%)
    total_unanswered = client_unanswered + editor_unanswered
    unfollowed_score = max(0, 100 - (total_unanswered * 15))

    # Weighted total
    weighted_score = (
        task_score * 0.40 +
        client_score * 0.20 +
        editor_score * 0.20 +
        proactive_score * 0.10 +
        unfollowed_score * 0.10
    )

    # Convert to letter grade
    if weighted_score >= 90:
        grade = "A"
        grade_label = "EXCELLENT"
        summary = "Outstanding day. All critical tasks handled, proactive communication."
    elif weighted_score >= 75:
        grade = "B"
        grade_label = "GOOD"
        summary = "Good day. Core deliverables done with minor gaps."
    elif weighted_score >= 60:
        grade = "C"
        grade_label = "FAIR"
        summary = "Fair day. Some tasks or communications missed."
    elif weighted_score >= 40:
        grade = "D"
        grade_label = "POOR"
        summary = "Below expectations. Multiple tasks missed or significant communication gaps."
    else:
        grade = "F"
        grade_label = "CRITICAL"
        summary = "Critical day. Major issues requiring immediate attention."

    return {
        "success": True,
        "grade": grade,
        "grade_label": grade_label,
        "score": round(weighted_score, 1),
        "summary": summary,
        "breakdown": {
            "task_completion": {"score": round(task_score, 1), "weight": "40%",
                                "detail": f"{overdue_count} overdue of {total_active} active videos"},
            "client_responsiveness": {"score": round(client_score, 1), "weight": "20%",
                                       "detail": f"{client_unanswered} unanswered client messages"},
            "editor_responsiveness": {"score": round(editor_score, 1), "weight": "20%",
                                       "detail": f"{editor_unanswered} unanswered editor messages"},
            "proactive_followups": {"score": round(proactive_score, 1), "weight": "10%",
                                     "detail": f"{upcoming_count} videos due in 1-2 days"},
            "unfollowed_messages": {"score": round(unfollowed_score, 1), "weight": "10%",
                                     "detail": f"{total_unanswered} total unanswered messages"},
        },
        "date": str(today),
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: day_rating.py <action> '<json_params>'"}))
        sys.exit(1)

    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON params"}))
            sys.exit(1)

    if action == "rate_day":
        result = rate_day()
    else:
        result = {"error": f"Unknown action: {action}"}
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
