#!/usr/bin/env python3
"""
Slack Read Tool
Access information from Slack workspace - messages, channels, users
"""

import json
import os
import sys
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def main():
    """Read information from Slack workspace"""

    # Get Slack token from environment (prefer User Token for full access)
    slack_token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
    if not slack_token:
        print(json.dumps({
            "error": "SLACK_USER_TOKEN or SLACK_BOT_TOKEN not found in environment variables"
        }))
        sys.exit(1)

    # Parse input arguments
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action parameter. Usage: slack_read.py <action> [params_json]"
        }))
        sys.exit(1)

    action = sys.argv[1]

    # Parse JSON params if provided
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            # Fallback to positional args for backward compatibility
            params = {"arg1": sys.argv[2]} if len(sys.argv) > 2 else {}
            if len(sys.argv) > 3:
                params["arg2"] = sys.argv[3]

    client = WebClient(token=slack_token)

    try:
        if action == "list_channels":
            # List all channels in workspace
            result = client.conversations_list(
                types="public_channel,private_channel"
            )
            channels = [
                {
                    "id": channel["id"],
                    "name": channel["name"],
                    "is_private": channel["is_private"],
                    "num_members": channel.get("num_members", 0)
                }
                for channel in result["channels"]
            ]
            print(json.dumps({
                "channels": channels,
                "count": len(channels)
            }))

        elif action == "read_messages":
            # Read messages from a specific channel
            channel_id = params.get("channel_id") or params.get("arg1")
            if not channel_id:
                print(json.dumps({
                    "error": "Missing channel_id parameter"
                }))
                sys.exit(1)

            limit = int(params.get("limit", 50))

            result = client.conversations_history(
                channel=channel_id,
                limit=limit
            )

            messages = []
            for msg in result["messages"]:
                # Get user info if message has user
                user_name = "Unknown"
                if "user" in msg:
                    try:
                        user_info = client.users_info(user=msg["user"])
                        user_name = user_info["user"].get("real_name", user_info["user"].get("name", "Unknown"))
                    except:
                        user_name = msg["user"]

                messages.append({
                    "text": msg.get("text", ""),
                    "user": user_name,
                    "timestamp": msg["ts"],
                    "formatted_time": datetime.fromtimestamp(float(msg["ts"])).strftime("%Y-%m-%d %H:%M:%S")
                })

            print(json.dumps({
                "messages": messages,
                "count": len(messages),
                "channel_id": channel_id
            }))

        elif action == "search_messages":
            # Search messages across workspace
            query = params.get("query") or params.get("arg1")
            if not query:
                print(json.dumps({
                    "error": "Missing query parameter"
                }))
                sys.exit(1)
            result = client.search_messages(query=query)

            messages = []
            for msg in result["messages"]["matches"]:
                messages.append({
                    "text": msg.get("text", ""),
                    "user": msg.get("username", "Unknown"),
                    "channel": msg.get("channel", {}).get("name", "Unknown"),
                    "timestamp": msg.get("ts", ""),
                    "permalink": msg.get("permalink", "")
                })

            print(json.dumps({
                "messages": messages,
                "count": len(messages),
                "query": query
            }))

        elif action == "list_users":
            # List all users in workspace
            result = client.users_list()
            users = [
                {
                    "id": user["id"],
                    "name": user.get("real_name", user.get("name", "Unknown")),
                    "email": user.get("profile", {}).get("email", ""),
                    "is_bot": user.get("is_bot", False)
                }
                for user in result["members"]
                if not user.get("deleted", False)
            ]
            print(json.dumps({
                "users": users,
                "count": len(users)
            }))

        else:
            print(json.dumps({
                "error": f"Unknown action: {action}",
                "available_actions": ["list_channels", "read_messages", "search_messages", "list_users"]
            }))
            sys.exit(1)

    except SlackApiError as e:
        print(json.dumps({
            "error": f"Slack API error: {e.response['error']}"
        }))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "error": f"Unexpected error: {str(e)}"
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
