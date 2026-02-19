#!/usr/bin/env python3
"""
Status Change Monitor - Detect Airtable status transitions and trigger notifications.

Uses a cache file (.tmp/status_cache.json) to track previous statuses.
First run caches everything without alerting (avoids false alerts).

Actions:
    check_qc_submissions     - Videos that moved to '60 - QC' status
    check_upcoming_deadlines - Videos with deadline = tomorrow that aren't done

Usage:
    python status_change_monitor.py check_qc_submissions '{}'
    python status_change_monitor.py check_upcoming_deadlines '{"days_ahead": 1}'
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
from utils import format_video_ref, get_client_map, resolve_editor_name

CACHE_DIR = Path(__file__).parent.parent.parent / ".tmp"
CACHE_FILE = CACHE_DIR / "status_cache.json"


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


def _load_cache() -> dict:
    """Load status cache from disk."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache: dict):
    """Save status cache to disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def check_qc_submissions() -> dict:
    """Detect videos that moved to QC status since last check.

    Returns videos that transitioned TO '60 - QC' (or similar QC statuses)
    since the last run. On first run, caches all statuses without alerting.
    """
    client_map = get_client_map()

    # Get all active videos
    records = _get_airtable_records(
        "Videos",
        filter_formula="{Editing Status} != '100 - Scheduled - DONE'",
        fields=["Video ID", "Client", "Video Number", "Format",
                "Editing Status", "Assigned Editor", "Editor's Name", "Deadline"]
    )

    cache = _load_cache()
    is_first_run = len(cache) == 0

    new_qc_submissions = []
    updated_cache = {}

    for record in records:
        rid = record["id"]
        fields = record["fields"]
        current_status = fields.get("Editing Status", "")
        previous_status = cache.get(rid, {}).get("status", "")

        updated_cache[rid] = {"status": current_status}

        # Skip if first run (just caching)
        if is_first_run:
            continue

        # Detect transition TO QC status
        qc_statuses = ["60 - Internal Review", "60 - Submitted for QC"]
        if current_status in qc_statuses and previous_status not in qc_statuses:
            display_name = format_video_ref(fields, client_map)
            editor = resolve_editor_name(fields)

            # Resolve client name for suggested message
            client_ids = fields.get("Client", [])
            client_name = "the client"
            if client_ids and client_map:
                cid = client_ids[0] if isinstance(client_ids, list) else client_ids
                client_name = client_map.get(cid, "the client")

            new_qc_submissions.append({
                "video_ref": display_name,
                "editor": editor,
                "client": client_name,
                "previous_status": previous_status,
                "current_status": current_status,
                "deadline": fields.get("Deadline", ""),
                "suggested_client_message": f"We're close to the finish line on your latest video! We're doing final quality checks now.",
            })

    _save_cache(updated_cache)

    return {
        "success": True,
        "items": new_qc_submissions,
        "count": len(new_qc_submissions),
        "first_run": is_first_run,
        "total_tracked": len(updated_cache),
    }


def check_upcoming_deadlines(days_ahead: int = 1) -> dict:
    """Find videos with deadline tomorrow (or within days_ahead) that aren't done.

    Returns editor reminders for videos with upcoming deadlines.
    """
    client_map = get_client_map()
    today = datetime.now().date()
    target_date = today + timedelta(days=days_ahead)

    records = _get_airtable_records(
        "Videos",
        filter_formula="AND({Editing Status} != '100 - Scheduled - DONE', {Deadline} != '')",
        fields=["Video ID", "Client", "Video Number", "Format",
                "Editing Status", "Assigned Editor", "Editor's Name", "Deadline"]
    )

    upcoming = []
    for record in records:
        fields = record["fields"]
        deadline_str = fields.get("Deadline", "")

        if not deadline_str:
            continue

        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        days_until = (deadline - today).days

        if 0 <= days_until <= days_ahead:
            display_name = format_video_ref(fields, client_map)
            editor = resolve_editor_name(fields)

            upcoming.append({
                "video_ref": display_name,
                "editor": editor,
                "deadline": deadline_str,
                "days_until": days_until,
                "status": fields.get("Editing Status", ""),
                "suggested_editor_message": f"Heads up — {display_name} deadline is {'today' if days_until == 0 else 'tomorrow'}! Current status: {fields.get('Editing Status', '')}",
            })

    # Sort by deadline (soonest first)
    upcoming.sort(key=lambda x: x["days_until"])

    # Build human-readable summary for DM
    if upcoming:
        lines = [f"{len(upcoming)} upcoming deadline(s):"]
        for it in upcoming:
            day_label = "TODAY" if it["days_until"] == 0 else "tomorrow"
            lines.append(f"- {it['video_ref']} ({it['editor']}) — {day_label}, status: {it['status']}")
        summary = "\n".join(lines)
    else:
        summary = "No upcoming deadlines."

    return {
        "success": True,
        "items": upcoming,
        "count": len(upcoming),
        "summary": summary,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: status_change_monitor.py <action> '<json_params>'"}))
        sys.exit(1)

    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON params"}))
            sys.exit(1)

    if action == "check_qc_submissions":
        result = check_qc_submissions()
    elif action == "check_upcoming_deadlines":
        result = check_upcoming_deadlines(days_ahead=params.get("days_ahead", 1))
    else:
        result = {"error": f"Unknown action: {action}"}
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
