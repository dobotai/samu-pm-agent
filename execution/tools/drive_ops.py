#!/usr/bin/env python3
"""
Google Drive Operations - Read and write operations for Google Drive.

Credential-ready: works when GOOGLE_CREDENTIALS_JSON is set in .env.
Extends the existing drive_read.py with write capabilities.

Actions:
    list_files     - List files in a folder
    get_link       - Get shareable link for a file
    create_folder  - Create a new folder
    upload_file    - Upload a file to Drive
    download_file  - Download a file from Drive
    search         - Search for files by name

Usage:
    python drive_ops.py list_files '{"folder_id": "abc123"}'
    python drive_ops.py get_link '{"file_id": "abc123"}'
"""

import json
import os
import sys
import io
import base64
from pathlib import Path

try:
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

TMP_DIR = Path(__file__).parent.parent.parent / ".tmp"


def _get_drive_service():
    """Get authenticated Google Drive service. Returns None if not configured."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        return None, "google-api-python-client not installed"

    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        return None, "GOOGLE_CREDENTIALS_JSON not set in .env"

    try:
        # Decode base64 if needed
        try:
            creds_data = json.loads(base64.b64decode(creds_json))
        except Exception:
            creds_data = json.loads(creds_json)

        creds = service_account.Credentials.from_service_account_info(
            creds_data,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"Failed to authenticate: {str(e)}"


def _check_credentials():
    """Return error dict if credentials missing."""
    service, error = _get_drive_service()
    if not service:
        return {"success": False, "error": error}
    return None


def list_files(folder_id: str, page_size: int = 50) -> dict:
    """List files in a Drive folder."""
    service, error = _get_drive_service()
    if not service:
        return {"success": False, "error": error}

    try:
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(
            q=query,
            pageSize=page_size,
            fields="files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink)"
        ).execute()

        files = results.get("files", [])
        return {
            "success": True,
            "files": [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "type": f["mimeType"],
                    "size": f.get("size"),
                    "created": f.get("createdTime"),
                    "modified": f.get("modifiedTime"),
                    "link": f.get("webViewLink"),
                }
                for f in files
            ],
            "count": len(files),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_link(file_id: str) -> dict:
    """Get shareable link for a file."""
    service, error = _get_drive_service()
    if not service:
        return {"success": False, "error": error}

    try:
        # Make file shareable
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        file = service.files().get(
            fileId=file_id,
            fields="id, name, webViewLink, webContentLink"
        ).execute()

        return {
            "success": True,
            "name": file.get("name"),
            "view_link": file.get("webViewLink"),
            "download_link": file.get("webContentLink"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_folder(name: str, parent_id: str = None) -> dict:
    """Create a new folder in Drive."""
    service, error = _get_drive_service()
    if not service:
        return {"success": False, "error": error}

    try:
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = service.files().create(body=metadata, fields="id, webViewLink").execute()
        return {
            "success": True,
            "folder_id": folder["id"],
            "link": folder.get("webViewLink"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_file(file_path: str, folder_id: str = None, name: str = None) -> dict:
    """Upload a file to Drive."""
    service, error = _get_drive_service()
    if not service:
        return {"success": False, "error": error}

    try:
        from googleapiclient.http import MediaFileUpload

        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        metadata = {"name": name or path.name}
        if folder_id:
            metadata["parents"] = [folder_id]

        media = MediaFileUpload(str(path), resumable=True)
        file = service.files().create(
            body=metadata, media_body=media, fields="id, webViewLink"
        ).execute()

        return {
            "success": True,
            "file_id": file["id"],
            "link": file.get("webViewLink"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def download_file(file_id: str, output_path: str = None) -> dict:
    """Download a file from Drive."""
    service, error = _get_drive_service()
    if not service:
        return {"success": False, "error": error}

    try:
        from googleapiclient.http import MediaIoBaseDownload

        # Get file metadata
        file_meta = service.files().get(fileId=file_id, fields="name, size").execute()
        file_name = file_meta.get("name", "download")

        if not output_path:
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            output_path = str(TMP_DIR / file_name)

        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(output_path, "wb")
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        fh.close()

        return {
            "success": True,
            "path": output_path,
            "name": file_name,
            "size": file_meta.get("size"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def search(query: str, page_size: int = 20) -> dict:
    """Search for files by name."""
    service, error = _get_drive_service()
    if not service:
        return {"success": False, "error": error}

    try:
        q = f"name contains '{query}' and trashed = false"
        results = service.files().list(
            q=q,
            pageSize=page_size,
            fields="files(id, name, mimeType, webViewLink, parents)"
        ).execute()

        files = results.get("files", [])
        return {
            "success": True,
            "files": [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "type": f["mimeType"],
                    "link": f.get("webViewLink"),
                }
                for f in files
            ],
            "count": len(files),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: drive_ops.py <action> '<json_params>'"}))
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
        "list_files": lambda: list_files(params["folder_id"], params.get("page_size", 50)),
        "get_link": lambda: get_link(params["file_id"]),
        "create_folder": lambda: create_folder(params["name"], params.get("parent_id")),
        "upload_file": lambda: upload_file(params["file_path"], params.get("folder_id"), params.get("name")),
        "download_file": lambda: download_file(params["file_id"], params.get("output_path")),
        "search": lambda: search(params["query"], params.get("page_size", 20)),
    }

    if action in actions:
        result = actions[action]()
    else:
        result = {"error": f"Unknown action: {action}. Available: {list(actions.keys())}"}
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
