#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test reading messages from #youtube channel
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

# Use User Token for full channel access
slack_token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

print(f"[INFO] Using token type: {'User Token (full access)' if os.getenv('SLACK_USER_TOKEN') else 'Bot Token (limited access)'}")

# #youtube channel ID from test
channel_id = "C071G9U0UU8"

print("\n" + "="*60)
print("RECENT MESSAGES FROM #youtube")
print("="*60)

try:
    # Get recent messages
    result = client.conversations_history(
        channel=channel_id,
        limit=10
    )

    messages = result["messages"]

    if not messages:
        print("\nNo messages found in #youtube channel.")
    else:
        print(f"\nShowing {len(messages)} most recent messages:\n")

        for i, msg in enumerate(reversed(messages), 1):
            # Get user info
            user_name = "Unknown"
            if "user" in msg:
                try:
                    user_info = client.users_info(user=msg["user"])
                    user_name = user_info["user"].get("real_name", user_info["user"].get("name", "Unknown"))
                except:
                    user_name = msg["user"]
            elif "bot_id" in msg:
                user_name = "[Bot]"

            # Format timestamp
            timestamp = datetime.fromtimestamp(float(msg["ts"])).strftime("%Y-%m-%d %H:%M:%S")

            # Get message text
            text = msg.get("text", "[No text content]")

            print(f"{i}. [{timestamp}] {user_name}:")
            print(f"   {text}")
            print()

except Exception as e:
    print(f"\n[ERROR] {str(e)}")
