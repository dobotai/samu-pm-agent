#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check which channels the bot can read messages from
"""

import os
import sys
from dotenv import load_dotenv
from slack_sdk import WebClient

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

slack_token = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

print("\n" + "="*60)
print("CHECKING CHANNEL ACCESS")
print("="*60)

try:
    # List all channels
    all_channels = client.conversations_list(types="public_channel,private_channel")

    print("\nAll channels in workspace:")
    for channel in all_channels["channels"]:
        channel_type = "[Private]" if channel.get('is_private') else "[Public]"
        is_member = channel.get('is_member', False)
        member_status = "[BOT IS MEMBER]" if is_member else "[NOT MEMBER]"

        print(f"\n  {channel_type} #{channel['name']} (ID: {channel['id']})")
        print(f"  {member_status}")

        # Try to read messages if bot is a member
        if is_member:
            try:
                history = client.conversations_history(channel=channel['id'], limit=1)
                msg_count = len(history.get('messages', []))
                print(f"  [CAN READ] {msg_count} message(s) accessible")
            except Exception as e:
                print(f"  [CANNOT READ] {str(e)}")

    print("\n" + "="*60)
    print("\nTO FIX: Invite the bot to #youtube channel:")
    print("  1. Go to #youtube channel in Slack")
    print("  2. Type: /invite @pm_agent")
    print("  3. Press Enter")
    print("="*60)

except Exception as e:
    print(f"\n[ERROR] {str(e)}")
