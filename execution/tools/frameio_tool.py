#!/usr/bin/env python3
"""
Frame.io Integration - Video review platform API.

Credential-ready: works the moment FRAMEIO_API_TOKEN is set in .env.
Gracefully returns error when credentials are missing.

Actions:
    list_projects   - List all Frame.io projects
    get_asset       - Get asset details by ID
    get_comments    - Get comments on an asset
    create_comment  - Add a QC comment to an asset
    get_review_link - Get shareable review link for an asset

Usage:
    python frameio_tool.py list_projects '{}'
    python frameio_tool.py get_review_link '{"asset_id": "abc123"}'
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

BASE_URL = "https://api.frame.io/v2"


def _get_headers():
    """Get Frame.io API headers. Returns None if token not configured."""
    token = os.getenv("FRAMEIO_API_TOKEN")
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _check_credentials():
    """Return error dict if credentials missing."""
    headers = _get_headers()
    if not headers:
        return {"success": False, "error": "FRAMEIO_API_TOKEN not set in .env"}
    return None


def list_projects(account_id: str = None) -> dict:
    """List all projects in the Frame.io account."""
    err = _check_credentials()
    if err:
        return err

    headers = _get_headers()

    # If no account_id, get the authenticated user's accounts first
    if not account_id:
        try:
            resp = requests.get(f"{BASE_URL}/me", headers=headers)
            resp.raise_for_status()
            me = resp.json()
            account_id = me.get("account_id")
            if not account_id:
                accounts = me.get("accounts", [])
                if accounts:
                    account_id = accounts[0].get("id")
        except Exception as e:
            return {"success": False, "error": f"Failed to get account: {str(e)}"}

    try:
        resp = requests.get(f"{BASE_URL}/accounts/{account_id}/projects", headers=headers)
        resp.raise_for_status()
        projects = resp.json()
        return {
            "success": True,
            "projects": [{"id": p["id"], "name": p["name"]} for p in projects],
            "count": len(projects),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_asset(asset_id: str) -> dict:
    """Get details of a specific asset."""
    err = _check_credentials()
    if err:
        return err

    try:
        resp = requests.get(f"{BASE_URL}/assets/{asset_id}", headers=_get_headers())
        resp.raise_for_status()
        asset = resp.json()
        return {
            "success": True,
            "asset": {
                "id": asset["id"],
                "name": asset.get("name"),
                "type": asset.get("type"),
                "status": asset.get("status"),
                "duration": asset.get("duration"),
                "filesize": asset.get("filesize"),
                "created_at": asset.get("inserted_at"),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_comments(asset_id: str) -> dict:
    """Get all comments on an asset."""
    err = _check_credentials()
    if err:
        return err

    try:
        resp = requests.get(f"{BASE_URL}/assets/{asset_id}/comments", headers=_get_headers())
        resp.raise_for_status()
        comments = resp.json()
        return {
            "success": True,
            "comments": [
                {
                    "id": c["id"],
                    "text": c.get("text"),
                    "timestamp": c.get("timestamp"),
                    "owner": c.get("owner", {}).get("name"),
                    "created_at": c.get("inserted_at"),
                }
                for c in comments
            ],
            "count": len(comments),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_comment(asset_id: str, text: str, timestamp: float = None) -> dict:
    """Add a comment to an asset (for QC feedback)."""
    err = _check_credentials()
    if err:
        return err

    payload = {"text": text}
    if timestamp is not None:
        payload["timestamp"] = timestamp

    try:
        resp = requests.post(
            f"{BASE_URL}/assets/{asset_id}/comments",
            headers=_get_headers(),
            json=payload,
        )
        resp.raise_for_status()
        comment = resp.json()
        return {
            "success": True,
            "comment_id": comment["id"],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_review_link(asset_id: str) -> dict:
    """Get or create a shareable review link for an asset."""
    err = _check_credentials()
    if err:
        return err

    try:
        resp = requests.get(f"{BASE_URL}/assets/{asset_id}", headers=_get_headers())
        resp.raise_for_status()
        asset = resp.json()

        # Check for existing review links
        review_links = asset.get("review_links", [])
        if review_links:
            return {
                "success": True,
                "review_link": review_links[0].get("short_url") or review_links[0].get("original_url"),
                "asset_name": asset.get("name"),
            }

        # Create a new review link
        parent_id = asset.get("parent_id")
        if parent_id:
            resp = requests.post(
                f"{BASE_URL}/projects/{parent_id}/review_links",
                headers=_get_headers(),
                json={"name": f"Review - {asset.get('name', 'Video')}",
                       "asset_ids": [asset_id]},
            )
            resp.raise_for_status()
            link = resp.json()
            return {
                "success": True,
                "review_link": link.get("short_url") or link.get("original_url"),
                "asset_name": asset.get("name"),
            }

        return {"success": False, "error": "Cannot create review link - no parent project found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: frameio_tool.py <action> '<json_params>'"}))
        sys.exit(1)

    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON params"}))
            sys.exit(1)

    actions = {
        "list_projects": lambda: list_projects(params.get("account_id")),
        "get_asset": lambda: get_asset(params["asset_id"]),
        "get_comments": lambda: get_comments(params["asset_id"]),
        "create_comment": lambda: create_comment(
            params["asset_id"], params["text"], params.get("timestamp")
        ),
        "get_review_link": lambda: get_review_link(params["asset_id"]),
    }

    if action in actions:
        result = actions[action]()
    else:
        result = {"error": f"Unknown action: {action}. Available: {list(actions.keys())}"}
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
