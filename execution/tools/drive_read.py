#!/usr/bin/env python3
"""
Google Drive Read Tool
Access files and folders from Google Drive
"""

import json
import os
import sys
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def get_drive_service():
    """Initialize Google Drive API service"""

    # Try to get credentials from environment variable (Railway deployment)
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

    if creds_json:
        # Decode base64 if needed
        try:
            creds_data = json.loads(base64.b64decode(creds_json))
        except:
            creds_data = json.loads(creds_json)

        credentials = service_account.Credentials.from_service_account_info(
            creds_data,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
    else:
        # Use local credentials.json file
        credentials = service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )

    return build('drive', 'v3', credentials=credentials)


def main():
    """Read information from Google Drive"""

    # Parse input arguments
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action parameter. Usage: drive_read.py <action> [params]"
        }))
        sys.exit(1)

    action = sys.argv[1]

    try:
        service = get_drive_service()

        if action == "list_files":
            # List files in Drive or specific folder
            folder_id = sys.argv[2] if len(sys.argv) > 2 else None
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 100

            query = ""
            if folder_id:
                query = f"'{folder_id}' in parents"

            # Add filter to exclude trashed items
            if query:
                query += " and trashed = false"
            else:
                query = "trashed = false"

            results = service.files().list(
                q=query,
                pageSize=limit,
                fields="files(id, name, mimeType, createdTime, modifiedTime, size, webViewLink, owners)"
            ).execute()

            files = []
            for file in results.get('files', []):
                files.append({
                    "id": file["id"],
                    "name": file["name"],
                    "type": file["mimeType"],
                    "is_folder": file["mimeType"] == "application/vnd.google-apps.folder",
                    "created": file.get("createdTime", ""),
                    "modified": file.get("modifiedTime", ""),
                    "size": file.get("size", "N/A"),
                    "link": file.get("webViewLink", ""),
                    "owner": file.get("owners", [{}])[0].get("displayName", "Unknown") if file.get("owners") else "Unknown"
                })

            print(json.dumps({
                "files": files,
                "count": len(files)
            }))

        elif action == "search_files":
            # Search for files by name
            if len(sys.argv) < 3:
                print(json.dumps({
                    "error": "Missing query parameter"
                }))
                sys.exit(1)

            query_text = sys.argv[2]
            query = f"name contains '{query_text}' and trashed = false"

            results = service.files().list(
                q=query,
                pageSize=50,
                fields="files(id, name, mimeType, modifiedTime, webViewLink)"
            ).execute()

            files = []
            for file in results.get('files', []):
                files.append({
                    "id": file["id"],
                    "name": file["name"],
                    "type": file["mimeType"],
                    "modified": file.get("modifiedTime", ""),
                    "link": file.get("webViewLink", "")
                })

            print(json.dumps({
                "files": files,
                "count": len(files),
                "query": query_text
            }))

        elif action == "get_file_info":
            # Get detailed information about a specific file
            if len(sys.argv) < 3:
                print(json.dumps({
                    "error": "Missing file_id parameter"
                }))
                sys.exit(1)

            file_id = sys.argv[2]

            file = service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, description, createdTime, modifiedTime, size, webViewLink, owners, permissions"
            ).execute()

            print(json.dumps({
                "id": file["id"],
                "name": file["name"],
                "type": file["mimeType"],
                "description": file.get("description", ""),
                "created": file.get("createdTime", ""),
                "modified": file.get("modifiedTime", ""),
                "size": file.get("size", "N/A"),
                "link": file.get("webViewLink", ""),
                "owner": file.get("owners", [{}])[0].get("displayName", "Unknown") if file.get("owners") else "Unknown",
                "shared_with": len(file.get("permissions", [])) - 1  # Subtract owner
            }))

        elif action == "list_recent":
            # List recently modified files
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20

            results = service.files().list(
                q="trashed = false",
                pageSize=limit,
                orderBy="modifiedTime desc",
                fields="files(id, name, mimeType, modifiedTime, webViewLink)"
            ).execute()

            files = []
            for file in results.get('files', []):
                files.append({
                    "id": file["id"],
                    "name": file["name"],
                    "type": file["mimeType"],
                    "modified": file.get("modifiedTime", ""),
                    "link": file.get("webViewLink", "")
                })

            print(json.dumps({
                "files": files,
                "count": len(files)
            }))

        else:
            print(json.dumps({
                "error": f"Unknown action: {action}",
                "available_actions": ["list_files", "search_files", "get_file_info", "list_recent"]
            }))
            sys.exit(1)

    except HttpError as e:
        print(json.dumps({
            "error": f"Google Drive API error: {str(e)}"
        }))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "error": f"Unexpected error: {str(e)}"
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
