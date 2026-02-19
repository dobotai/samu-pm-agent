#!/usr/bin/env python3
"""
YouTube Scheduling - Upload and schedule videos via YouTube Data API v3.

Credential-ready: works when YOUTUBE_CLIENT_SECRETS_JSON is set.
Per-client OAuth tokens stored at .tmp/youtube_tokens/{client}.json.

Quota: 10,000 units/day. Upload = 1,600 units (~6 uploads/day max).

Actions:
    list_channels    - List authenticated channels
    upload_video     - Upload a video file
    schedule_video   - Upload + schedule for specific date/time
    update_metadata  - Update title, description, tags
    get_status       - Get video processing status
    list_scheduled   - List upcoming scheduled videos

Usage:
    python youtube_tool.py list_channels '{"client": "taylor"}'
    python youtube_tool.py schedule_video '{"client": "taylor", "file_path": "/path/to/video.mp4", ...}'
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

TOKEN_DIR = Path(__file__).parent.parent.parent / ".tmp" / "youtube_tokens"


def _get_youtube_service(client_name: str):
    """Get authenticated YouTube service for a specific client.

    Each client's YouTube channel requires separate OAuth tokens.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        return None, "google-api-python-client or google-auth-oauthlib not installed"

    client_secrets = os.getenv("YOUTUBE_CLIENT_SECRETS_JSON")
    if not client_secrets:
        return None, "YOUTUBE_CLIENT_SECRETS_JSON not set in .env"

    token_file = TOKEN_DIR / f"{client_name.lower()}.json"
    creds = None

    # Load existing token
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file))
        except Exception:
            pass

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_DIR.mkdir(parents=True, exist_ok=True)
            token_file.write_text(creds.to_json())
        except Exception:
            creds = None

    if not creds or not creds.valid:
        return None, f"No valid token for client '{client_name}'. Run OAuth flow first: python youtube_tool.py authorize '{{\"{client_name}\"}}'"

    try:
        service = build("youtube", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, str(e)


def list_channels(client: str) -> dict:
    """List YouTube channels for the authenticated client."""
    service, error = _get_youtube_service(client)
    if not service:
        return {"success": False, "error": error}

    try:
        resp = service.channels().list(part="snippet,statistics", mine=True).execute()
        channels = resp.get("items", [])
        return {
            "success": True,
            "channels": [
                {
                    "id": ch["id"],
                    "title": ch["snippet"]["title"],
                    "subscribers": ch["statistics"].get("subscriberCount"),
                    "videos": ch["statistics"].get("videoCount"),
                }
                for ch in channels
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def schedule_video(client: str, file_path: str, title: str,
                    description: str = "", tags: list = None,
                    schedule_time: str = None, thumbnail_path: str = None,
                    category_id: str = "22", privacy: str = "private") -> dict:
    """Upload and schedule a video on YouTube.

    Args:
        client: Client name (for token lookup)
        file_path: Path to the video file
        title: Video title
        description: Video description
        tags: List of tags
        schedule_time: ISO 8601 datetime for scheduling (e.g., "2026-02-15T16:00:00Z")
        thumbnail_path: Path to thumbnail image
        category_id: YouTube category ID (22 = People & Blogs)
        privacy: "private", "unlisted", or "public"
    """
    service, error = _get_youtube_service(client)
    if not service:
        return {"success": False, "error": error}

    path = Path(file_path)
    if not path.exists():
        return {"success": False, "error": f"Video file not found: {file_path}"}

    try:
        from googleapiclient.http import MediaFileUpload

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        if schedule_time:
            body["status"]["publishAt"] = schedule_time
            body["status"]["privacyStatus"] = "private"

        media = MediaFileUpload(str(path), resumable=True, chunksize=10 * 1024 * 1024)

        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            _, response = request.next_chunk()

        video_id = response["id"]

        # Upload thumbnail if provided
        if thumbnail_path:
            thumb_path = Path(thumbnail_path)
            if thumb_path.exists():
                service.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumb_path)),
                ).execute()

        return {
            "success": True,
            "video_id": video_id,
            "url": f"https://youtube.com/watch?v={video_id}",
            "scheduled": schedule_time,
            "title": title,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_metadata(client: str, video_id: str, title: str = None,
                     description: str = None, tags: list = None) -> dict:
    """Update video metadata."""
    service, error = _get_youtube_service(client)
    if not service:
        return {"success": False, "error": error}

    try:
        # Get current video data
        current = service.videos().list(part="snippet", id=video_id).execute()
        items = current.get("items", [])
        if not items:
            return {"success": False, "error": f"Video {video_id} not found"}

        snippet = items[0]["snippet"]
        if title:
            snippet["title"] = title
        if description:
            snippet["description"] = description
        if tags:
            snippet["tags"] = tags

        service.videos().update(
            part="snippet",
            body={"id": video_id, "snippet": snippet},
        ).execute()

        return {"success": True, "video_id": video_id, "updated": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_status(client: str, video_id: str) -> dict:
    """Get video processing/publishing status."""
    service, error = _get_youtube_service(client)
    if not service:
        return {"success": False, "error": error}

    try:
        resp = service.videos().list(
            part="status,processingDetails,snippet", id=video_id
        ).execute()
        items = resp.get("items", [])
        if not items:
            return {"success": False, "error": f"Video {video_id} not found"}

        item = items[0]
        status = item.get("status", {})
        processing = item.get("processingDetails", {})

        return {
            "success": True,
            "video_id": video_id,
            "title": item.get("snippet", {}).get("title"),
            "privacy": status.get("privacyStatus"),
            "publish_at": status.get("publishAt"),
            "upload_status": status.get("uploadStatus"),
            "processing_status": processing.get("processingStatus"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_scheduled(client: str) -> dict:
    """List upcoming scheduled (private) videos."""
    service, error = _get_youtube_service(client)
    if not service:
        return {"success": False, "error": error}

    try:
        # Search for private videos (scheduled ones are private until publish time)
        resp = service.search().list(
            part="snippet",
            forMine=True,
            type="video",
            maxResults=25,
        ).execute()

        video_ids = [item["id"]["videoId"] for item in resp.get("items", [])]
        if not video_ids:
            return {"success": True, "scheduled": [], "count": 0}

        # Get status details
        details = service.videos().list(
            part="status,snippet",
            id=",".join(video_ids),
        ).execute()

        scheduled = []
        for item in details.get("items", []):
            status = item.get("status", {})
            if status.get("publishAt"):
                scheduled.append({
                    "video_id": item["id"],
                    "title": item["snippet"]["title"],
                    "publish_at": status["publishAt"],
                    "privacy": status["privacyStatus"],
                })

        scheduled.sort(key=lambda x: x["publish_at"])

        return {"success": True, "scheduled": scheduled, "count": len(scheduled)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: youtube_tool.py <action> '<json_params>'"}))
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
        "list_channels": lambda: list_channels(params.get("client", "")),
        "schedule_video": lambda: schedule_video(
            client=params["client"], file_path=params["file_path"],
            title=params["title"], description=params.get("description", ""),
            tags=params.get("tags"), schedule_time=params.get("schedule_time"),
            thumbnail_path=params.get("thumbnail_path"),
        ),
        "upload_video": lambda: schedule_video(
            client=params["client"], file_path=params["file_path"],
            title=params["title"], description=params.get("description", ""),
            tags=params.get("tags"), thumbnail_path=params.get("thumbnail_path"),
        ),
        "update_metadata": lambda: update_metadata(
            client=params["client"], video_id=params["video_id"],
            title=params.get("title"), description=params.get("description"),
            tags=params.get("tags"),
        ),
        "get_status": lambda: get_status(params["client"], params["video_id"]),
        "list_scheduled": lambda: list_scheduled(params.get("client", "")),
    }

    if action in actions:
        result = actions[action]()
    else:
        result = {"error": f"Unknown action: {action}. Available: {list(actions.keys())}"}
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
