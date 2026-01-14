#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
List all channels including private ones
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

slack_token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

print("\n" + "="*60)
print("LISTING ALL CHANNELS (PUBLIC AND PRIVATE)")
print("="*60)

try:
    # Try to list all channels including private
    all_channels = client.conversations_list(types="public_channel,private_channel")

    print(f"\n[SUCCESS] Found {len(all_channels['channels'])} total channels:\n")

    for ch in all_channels["channels"]:
        channel_type = "[Private]" if ch.get('is_private') else "[Public] "
        print(f"  {channel_type} #{ch['name']} (ID: {ch['id']})")

except Exception as e:
    error_msg = str(e)
    if "missing_scope" in error_msg:
        print(f"\n[ERROR] Missing scope for private channels")
        print(f"        {error_msg}")
        print("\n[INFO] Listing PUBLIC channels only:\n")

        # List public channels only
        public_channels = client.conversations_list(types="public_channel")
        for ch in public_channels["channels"]:
            print(f"  [Public]  #{ch['name']} (ID: {ch['id']})")
    else:
        print(f"\n[ERROR] {error_msg}")
