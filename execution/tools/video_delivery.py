#!/usr/bin/env python3
"""
Video Delivery - Compose client delivery messages from Airtable data.

Checks video record for Frame.io and Drive links. If present, composes
a full delivery message from message templates. If missing, returns what
links need to be provided manually.

Actions:
    prepare_client_delivery - Compose delivery message for a video

Usage:
    python video_delivery.py prepare_client_delivery '{"record_id": "recXXX"}'
    python video_delivery.py prepare_client_delivery '{"video_ref": "Taylor Video #11"}'
"""

import json
import os
import sys
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
from utils import format_video_ref, get_client_map

# Load message templates
TEMPLATES_FILE = Path(__file__).parent.parent.parent / "config" / "message_templates.json"


def _load_template(template_id):
    """Load a message template by ID."""
    if not TEMPLATES_FILE.exists():
        return None
    try:
        data = json.loads(TEMPLATES_FILE.read_text())
        for t in data.get("templates", []):
            if t["id"] == template_id:
                return t
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _get_airtable_record(record_id):
    """Fetch a single Airtable record by ID."""
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    if not api_key or not base_id:
        return None

    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"https://api.airtable.com/v0/{base_id}/Videos/{record_id}"

    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return {"id": data["id"], "fields": data.get("fields", {})}
    except Exception:
        return None


def _search_video_by_ref(video_ref):
    """Search for a video by display reference (e.g., 'Taylor Video #11').

    Filters by BOTH Video Number AND Client name to avoid returning
    the wrong client's video when multiple clients share a video number.
    """
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    if not api_key or not base_id:
        return None

    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"https://api.airtable.com/v0/{base_id}/Videos"

    # Extract video number from ref (e.g., "Taylor Video #11" → "11")
    parts = video_ref.split("#")
    if len(parts) < 2:
        return None
    video_num = parts[-1].strip()

    # Extract client name from ref (e.g., "Taylor Video #11" → "Taylor")
    # Format is "ClientName Video #X" or "ClientName Shorts #X"
    ref_lower = video_ref.lower()
    client_name = None
    for keyword in [" video ", " shorts "]:
        idx = ref_lower.find(keyword)
        if idx > 0:
            client_name = video_ref[:idx].strip()
            break

    # Filter by Video Number
    params = [("filterByFormula", f"{{Video Number}} = '{video_num}'")]

    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        records = resp.json().get("records", [])
        if not records:
            return None

        # If we have a client name, resolve it to find the right record
        if client_name and len(records) > 1:
            client_map = get_client_map()
            for r in records:
                fields = r.get("fields", {})
                client_ids = fields.get("Client", [])
                if client_ids and client_map:
                    cid = client_ids[0] if isinstance(client_ids, list) else client_ids
                    resolved_name = client_map.get(cid, "")
                    if resolved_name.lower() == client_name.lower():
                        return {"id": r["id"], "fields": fields}

        # Fall back to first result
        r = records[0]
        return {"id": r["id"], "fields": r.get("fields", {})}
    except Exception:
        pass
    return None


def prepare_client_delivery(record_id: str = None, video_ref: str = None) -> dict:
    """Compose a client delivery message for a video.

    Looks up the video record, checks for Frame.io and Drive links,
    and composes a delivery message using templates.
    """
    # Find the record
    record = None
    if record_id:
        record = _get_airtable_record(record_id)
    elif video_ref:
        record = _search_video_by_ref(video_ref)

    if not record:
        return {"success": False, "error": "Video not found"}

    fields = record["fields"]
    client_map = get_client_map()
    display_name = format_video_ref(fields, client_map)

    # Resolve client name
    client_ids = fields.get("Client", [])
    client_name = "there"
    if client_ids and client_map:
        cid = client_ids[0] if isinstance(client_ids, list) else client_ids
        client_name = client_map.get(cid, "there")

    # Check for links in Airtable fields
    frame_link = (
        fields.get("Frame.io Link") or
        fields.get("Frame Link") or
        fields.get("Review Link") or
        None
    )
    drive_link = (
        fields.get("Drive Link") or
        fields.get("Drive Folder") or
        fields.get("Folder Link") or
        None
    )

    missing_links = []
    if not frame_link:
        missing_links.append("frame.io")
    if not drive_link:
        missing_links.append("drive")

    # Load delivery template
    template = _load_template("client_video_review")

    if missing_links:
        return {
            "success": True,
            "ready": False,
            "video_ref": display_name,
            "client": client_name,
            "requires_links": missing_links,
            "note": f"Need {' and '.join(missing_links)} link(s) to send delivery message for {display_name}",
        }

    # Compose message
    if template:
        message = template["template"].format(
            client_name=client_name,
            frame_link=frame_link,
            drive_link=drive_link,
        )
    else:
        message = (
            f"Hey @{client_name}, new video is ready for checking: {frame_link}\n"
            f"Folder with thumbnail: {drive_link}\n\n"
            f"If it's approved, let us know and we're scheduling it! "
            f"If you have any revisions, feel free to put them in frame :)"
        )

    return {
        "success": True,
        "ready": True,
        "video_ref": display_name,
        "client": client_name,
        "message": message,
        "frame_link": frame_link,
        "drive_link": drive_link,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: video_delivery.py <action> '<json_params>'"}))
        sys.exit(1)

    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON params"}))
            sys.exit(1)

    if action == "prepare_client_delivery":
        result = prepare_client_delivery(
            record_id=params.get("record_id"),
            video_ref=params.get("video_ref"),
        )
    else:
        result = {"error": f"Unknown action: {action}"}
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
