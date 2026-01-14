#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Find which editors have been active today in Slack
"""

import os
import sys
from dotenv import load_dotenv
from slack_sdk import WebClient
from datetime import datetime, timedelta

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

slack_token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

print("\n" + "="*60)
print("EDITORS ACTIVE TODAY")
print("="*60)

try:
    # Get start of today (midnight)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_timestamp = today_start.timestamp()

    print(f"\n[INFO] Searching for activity since: {today_start.strftime('%Y-%m-%d %H:%M:%S')}")

    # List all channels
    all_channels = client.conversations_list(types="public_channel,private_channel")

    # Find channels with "editing" in the name
    editing_channels = [ch for ch in all_channels["channels"] if "editing" in ch["name"].lower()]

    print(f"\n[FOUND] {len(editing_channels)} editing channels:")
    for ch in editing_channels:
        print(f"  - #{ch['name']}")

    # Track active editors
    active_editors = {}

    # Check each editing channel for today's messages
    for channel in editing_channels:
        channel_id = channel["id"]
        channel_name = channel["name"]

        try:
            # Get messages from today
            result = client.conversations_history(
                channel=channel_id,
                oldest=str(today_timestamp),
                limit=100
            )

            messages = result.get("messages", [])

            if messages:
                # Count messages per user
                for msg in messages:
                    if "user" in msg and msg.get("subtype") not in ["channel_join", "channel_leave"]:
                        user_id = msg["user"]

                        # Get user info if we haven't seen them yet
                        if user_id not in active_editors:
                            try:
                                user_info = client.users_info(user=user_id)
                                user_name = user_info["user"].get("real_name", user_info["user"].get("name", "Unknown"))
                                active_editors[user_id] = {
                                    "name": user_name,
                                    "channels": set(),
                                    "message_count": 0
                                }
                            except:
                                continue

                        active_editors[user_id]["channels"].add(channel_name)
                        active_editors[user_id]["message_count"] += 1

        except Exception as e:
            print(f"  [SKIP] Could not read #{channel_name}: {str(e)}")
            continue

    # Also check client channels for editor activity
    client_channels = [ch for ch in all_channels["channels"] if "client" in ch["name"].lower()]

    print(f"\n[FOUND] {len(client_channels)} client channels")
    print(f"[INFO] Checking for editor activity in client channels...\n")

    for channel in client_channels:
        channel_id = channel["id"]
        channel_name = channel["name"]

        try:
            # Get messages from today
            result = client.conversations_history(
                channel=channel_id,
                oldest=str(today_timestamp),
                limit=100
            )

            messages = result.get("messages", [])

            for msg in messages:
                if "user" in msg and msg.get("subtype") not in ["channel_join", "channel_leave"]:
                    user_id = msg["user"]

                    # Get user info
                    if user_id not in active_editors:
                        try:
                            user_info = client.users_info(user=user_id)
                            user_name = user_info["user"].get("real_name", user_info["user"].get("name", "Unknown"))
                            active_editors[user_id] = {
                                "name": user_name,
                                "channels": set(),
                                "message_count": 0
                            }
                        except:
                            continue

                    active_editors[user_id]["channels"].add(channel_name)
                    active_editors[user_id]["message_count"] += 1

        except:
            continue

    # Display results
    print("="*60)
    print("ACTIVE EDITORS TODAY")
    print("="*60)

    if not active_editors:
        print("\n[INFO] No editor activity found today")
    else:
        # Sort by message count
        sorted_editors = sorted(active_editors.items(), key=lambda x: x[1]["message_count"], reverse=True)

        print(f"\n[FOUND] {len(sorted_editors)} active editors:\n")

        for user_id, data in sorted_editors:
            print(f"  {data['name']}")
            print(f"    Messages: {data['message_count']}")
            print(f"    Channels: {', '.join(['#' + ch for ch in sorted(data['channels'])])}")
            print()

except Exception as e:
    print(f"\n[ERROR] {str(e)}")
    import traceback
    traceback.print_exc()
