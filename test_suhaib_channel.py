#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Summarize what's happening in Suhaib's editing channel
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
print("SUHAIB'S EDITING CHANNEL SUMMARY")
print("="*60)

try:
    # Find Suhaib's channel
    all_channels = client.conversations_list(types="public_channel,private_channel")
    suhaib_channels = [ch for ch in all_channels["channels"] if "suhaib" in ch["name"].lower()]

    if not suhaib_channels:
        print("\n[ERROR] Could not find Suhaib's channel")
        sys.exit(1)

    channel = suhaib_channels[0]
    channel_id = channel["id"]
    channel_name = channel["name"]

    print(f"\n[FOUND] Channel: #{channel_name} (ID: {channel_id})")
    print(f"        Type: {'Private' if channel.get('is_private') else 'Public'}")

    # Get recent messages (last 50)
    print(f"\n[READING] Fetching recent messages from #{channel_name}...")
    result = client.conversations_history(
        channel=channel_id,
        limit=50
    )

    messages = result["messages"]

    if not messages:
        print(f"\n[INFO] No messages found in #{channel_name}")
        sys.exit(0)

    # Filter out system messages
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
            user_name = "[Airtable Bot]"
            users_involved.add(user_name)

        text = msg.get("text", "")
        if text:
            timestamp = datetime.fromtimestamp(float(msg["ts"]))
            conversation_messages.append({
                "user": user_name,
                "text": text,
                "timestamp": timestamp
            })

    # Sort messages chronologically (oldest first)
    conversation_messages.sort(key=lambda x: x["timestamp"])

    # Separate today's messages from historical
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_messages = [m for m in conversation_messages if m["timestamp"] >= today_start]
    historical_messages = [m for m in conversation_messages if m["timestamp"] < today_start]

    print("\n" + "="*60)
    print(f"CHANNEL OVERVIEW: #{channel_name.upper()}")
    print("="*60)

    print(f"\nTotal messages: {len(conversation_messages)}")
    print(f"Participants: {', '.join(users_involved) if users_involved else 'None'}")

    if conversation_messages:
        print(f"\nDate range: {conversation_messages[0]['timestamp'].strftime('%Y-%m-%d')} to {conversation_messages[-1]['timestamp'].strftime('%Y-%m-%d')}")

    # Show today's activity
    if today_messages:
        print(f"\n" + "="*60)
        print(f"TODAY'S ACTIVITY ({len(today_messages)} messages)")
        print("="*60 + "\n")

        for i, msg in enumerate(today_messages, 1):
            time_str = msg['timestamp'].strftime("%H:%M")
            print(f"{i}. [{time_str}] {msg['user']}:")
            print(f"   {msg['text']}")
            print()
    else:
        print(f"\n[INFO] No messages today")

    # Show recent historical context (last 10 messages before today)
    if historical_messages:
        recent_history = historical_messages[-10:]
        print(f"\n" + "="*60)
        print(f"RECENT HISTORY (Last {len(recent_history)} messages before today)")
        print("="*60 + "\n")

        for i, msg in enumerate(recent_history, 1):
            date_str = msg['timestamp'].strftime("%Y-%m-%d %H:%M")
            print(f"{i}. [{date_str}] {msg['user']}:")
            print(f"   {msg['text']}")
            print()

except Exception as e:
    print(f"\n[ERROR] {str(e)}")
    import traceback
    traceback.print_exc()
