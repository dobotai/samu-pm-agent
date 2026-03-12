#!/usr/bin/env python3
"""
Shared utilities for PM agent tools.

Provides:
    - get_client_map()    : Fetch Clients table → {record_id: name} lookup
    - get_editor_map()    : Fetch Team table → {record_id: name} lookup
    - format_video_ref()  : Format video as "ClientName Video #X" (never raw IDs)

These address the #1 client complaint: raw Video IDs showing instead of
human-readable "ClientName Video #X" format.

Reference implementation: execution/editor_task_report.py lines 103-128
"""

import os
import requests
from typing import Dict, Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def _get_airtable_config():
    """Get Airtable API key and base ID from environment."""
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    return api_key, base_id


def _fetch_airtable_table(table_name: str, fields: list = None,
                          api_key: str = None, base_id: str = None) -> list:
    """Fetch all records from an Airtable table with pagination.

    Args:
        table_name: Name of the Airtable table
        fields: Optional list of field names to retrieve
        api_key: Airtable API key (falls back to env)
        base_id: Airtable base ID (falls back to env)

    Returns:
        List of record dicts with 'id' and 'fields' keys.
    """
    if not api_key or not base_id:
        env_key, env_base = _get_airtable_config()
        api_key = api_key or env_key
        base_id = base_id or env_base

    if not api_key or not base_id:
        return []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    params = {}
    if fields:
        for f in fields:
            params.setdefault("fields[]", [])
        # requests handles list params correctly
        params = [("fields[]", f) for f in fields] if fields else []

    all_records = []
    offset = None

    while True:
        req_params = list(params) if isinstance(params, list) else []
        if offset:
            req_params.append(("offset", offset))

        try:
            response = requests.get(url, headers=headers, params=req_params)
            response.raise_for_status()
            data = response.json()
        except Exception:
            break

        for r in data.get("records", []):
            all_records.append({
                "id": r["id"],
                "fields": r.get("fields", {}),
            })

        offset = data.get("offset")
        if not offset:
            break

    return all_records


def get_client_map(api_key: str = None, base_id: str = None) -> Dict[str, str]:
    """Fetch Clients table and return {record_id: client_name} map.

    The Airtable "Client" field on Videos is a LINKED RECORD — it returns
    an array of record IDs like ['recXXX'], NOT the client name string.
    This function builds the lookup map needed to resolve those IDs.

    Args:
        api_key: Airtable API key (falls back to AIRTABLE_API_KEY env)
        base_id: Airtable base ID (falls back to AIRTABLE_BASE_ID env)

    Returns:
        Dict mapping record IDs to client names.
        Example: {"recABC123": "Taylor", "recDEF456": "Christian"}
    """
    records = _fetch_airtable_table("Clients", fields=["Name"],
                                     api_key=api_key, base_id=base_id)
    return {r["id"]: r["fields"].get("Name", "Unknown") for r in records}


def get_editor_map(api_key: str = None, base_id: str = None) -> Dict[str, str]:
    """Fetch Team table and return {record_id: editor_name} map.

    Same linked-record resolution pattern as get_client_map().

    Args:
        api_key: Airtable API key (falls back to AIRTABLE_API_KEY env)
        base_id: Airtable base ID (falls back to AIRTABLE_BASE_ID env)

    Returns:
        Dict mapping record IDs to team member names.
    """
    records = _fetch_airtable_table("Team", fields=["Name"],
                                     api_key=api_key, base_id=base_id)
    return {r["id"]: r["fields"].get("Name", "Unknown") for r in records}


def format_video_ref(fields: dict, client_map: Dict[str, str] = None) -> str:
    """Format a video record as 'ClientName Video #X'. Never returns raw IDs.

    This is THE canonical way to display video references. All tools MUST
    use this instead of fields.get('Video ID').

    Resolution order for client name:
    1. Resolve Client linked record ID via client_map (preferred)
    2. Fall back to "Client Name" direct field (some views have this)
    3. Fall back to "Unknown"

    Args:
        fields: The Airtable record's fields dict.
        client_map: {record_id: name} map from get_client_map(). Strongly
                    recommended — without it, linked record IDs can't be resolved.

    Returns:
        String like "Taylor Video #11" or "Christian Shorts #3".
        Never returns raw Video IDs or record IDs.
    """
    # Resolve client name from linked record
    client_name = "Unknown"
    client_ids = fields.get("Client", [])

    if client_map and client_ids:
        if isinstance(client_ids, list) and len(client_ids) > 0:
            client_name = client_map.get(client_ids[0], "Unknown")
        elif isinstance(client_ids, str):
            client_name = client_map.get(client_ids, "Unknown")

    # Fallback: some Airtable views expose a direct "Client Name" text field
    if client_name == "Unknown":
        client_name = (
            fields.get("Client Name") or
            fields.get("Client name") or
            "Unknown"
        )

    # Get video number
    video_num = fields.get("Video Number", "?")

    # Determine type (Video vs Shorts) from Format field
    fmt = str(fields.get("Format", "")).lower()
    video_type = "Shorts" if "short" in fmt else "Video"

    return f"{client_name} {video_type} #{video_num}"


def resolve_editor_name(fields: dict, editor_map: Dict[str, str] = None) -> str:
    """Resolve editor name from Airtable fields.

    Handles both direct name fields and linked record IDs.

    Args:
        fields: The Airtable record's fields dict.
        editor_map: {record_id: name} map from get_editor_map().

    Returns:
        Editor name string, or "Unassigned" if not found.
    """
    # Try direct name field first
    editor_name = fields.get("Editor's Name")
    if isinstance(editor_name, list):
        editor_name = editor_name[0] if editor_name else None
    if editor_name and not editor_name.startswith("rec"):
        return editor_name

    # Resolve from linked record
    editor_ids = fields.get("Assigned Editor", [])
    if editor_map and editor_ids:
        if isinstance(editor_ids, list) and len(editor_ids) > 0:
            return editor_map.get(editor_ids[0], "Unassigned")
        elif isinstance(editor_ids, str):
            return editor_map.get(editor_ids, "Unassigned")

    return editor_name or "Unassigned"
