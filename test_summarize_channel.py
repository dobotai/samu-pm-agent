#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Find and summarize messages from a channel
"""

import os
import sys
from dotenv import load_dotenv
from slack_sdk import WebClient
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

slack_token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

print("\n" + "="*60)
print("SEARCHING FOR TAYLOR CLIENT CHANNEL")
print("="*60)

try:
    # List all channels to find "taylor" channel
    all_channels = client.conversations_list(types="public_channel,private_channel")

    taylor_channels = [ch for ch in all_channels["channels"] if "taylor" in ch["name"].lower()]

    if not taylor_channels:
        print("\n[INFO] No channels found with 'taylor' in the name.")
        print("\nAvailable channels:")
        for ch in all_channels["channels"]:
            print(f"  - #{ch['name']}")
        sys.exit(0)

    # Use the first matching channel
    channel = taylor_channels[0]
    channel_id = channel["id"]
    channel_name = channel["name"]

    print(f"\n[FOUND] Channel: #{channel_name} (ID: {channel_id})")
    print(f"        Type: {'Private' if channel.get('is_private') else 'Public'}")

    # Get messages from the channel
    print(f"\n[READING] Fetching messages from #{channel_name}...")
    result = client.conversations_history(
        channel=channel_id,
        limit=50
    )

    messages = result["messages"]

    if not messages:
        print(f"\n[INFO] No messages found in #{channel_name}")
        sys.exit(0)

    # Filter out join/leave messages and organize by user
    conversation_messages = []
    users_involved = set()

    for msg in messages:
        # Skip system messages
        if msg.get("subtype") in ["channel_join", "channel_leave"]:
            continue

        # Get user info
        user_name = "Unknown"
        if "user" in msg:
            try:
                user_info = client.users_info(user=msg["user"])
                user_name = user_info["user"].get("real_name", user_info["user"].get("name", "Unknown"))
                users_involved.add(user_name)
            except:
                user_name = msg["user"]
        elif "bot_id" in msg:
            user_name = "[Bot]"

        text = msg.get("text", "")
        if text:
            timestamp = datetime.fromtimestamp(float(msg["ts"]))
            conversation_messages.append({
                "user": user_name,
                "text": text,
                "timestamp": timestamp
            })

    # Sort messages chronologically
    conversation_messages.sort(key=lambda x: x["timestamp"])

    print("\n" + "="*60)
    print(f"SUMMARY: #{channel_name.upper()} CHANNEL")
    print("="*60)

    print(f"\nTotal messages: {len(conversation_messages)}")
    print(f"Participants: {', '.join(users_involved) if users_involved else 'None'}")

    if conversation_messages:
        print(f"\nDate range: {conversation_messages[0]['timestamp'].strftime('%Y-%m-%d')} to {conversation_messages[-1]['timestamp'].strftime('%Y-%m-%d')}")

        print(f"\n\nMESSAGE HISTORY:\n")
        for i, msg in enumerate(conversation_messages, 1):
            date_str = msg['timestamp'].strftime("%Y-%m-%d %H:%M")
            print(f"{i}. [{date_str}] {msg['user']}:")
            print(f"   {msg['text']}")
            print()
    else:
        print("\n[INFO] No conversation messages found (only system messages)")

except Exception as e:
    print(f"\n[ERROR] {str(e)}")
    import traceback
    traceback.print_exc()
