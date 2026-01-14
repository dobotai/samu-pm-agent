#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick test script to verify Slack bot connection
"""

import os
import sys
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

slack_token = os.getenv("SLACK_BOT_TOKEN")

if not slack_token or slack_token == "xoxb-your-slack-bot-token-here":
    print("[ERROR] SLACK_BOT_TOKEN not configured in .env file")
    exit(1)

print(f"[OK] Token found: {slack_token[:20]}...")

try:
    client = WebClient(token=slack_token)

    # Test 1: Auth test
    print("\n[TEST] Testing authentication...")
    auth_response = client.auth_test()
    print(f"[PASS] Authenticated as: {auth_response['user']}")
    print(f"       Team: {auth_response['team']}")
    print(f"       Bot User ID: {auth_response['user_id']}")

    # Test 2: List channels
    print("\n[TEST] Testing channel access...")
    channels_response = client.conversations_list(types="public_channel,private_channel", limit=5)
    channels = channels_response['channels']
    print(f"[PASS] Can access {len(channels)} channels (showing first 5):")
    for channel in channels[:5]:
        channel_type = "[Private]" if channel.get('is_private') else "[Public]"
        print(f"       {channel_type} #{channel['name']} (ID: {channel['id']})")

    # Test 3: List users
    print("\n[TEST] Testing user access...")
    users_response = client.users_list(limit=5)
    users = [u for u in users_response['members'] if not u.get('deleted') and not u.get('is_bot')]
    print(f"[PASS] Can access {len(users)} users (showing first 5):")
    for user in users[:5]:
        name = user.get('real_name', user.get('name', 'Unknown'))
        email = user.get('profile', {}).get('email', 'No email')
        print(f"       {name} - {email}")

    print("\n" + "="*60)
    print("[SUCCESS] ALL TESTS PASSED! Slack bot is working correctly.")
    print("="*60)

except SlackApiError as e:
    print(f"\n[ERROR] Slack API Error: {e.response['error']}")
    print(f"        Details: {e.response.get('needed', 'Unknown scope issue')}")
    print("\n[HELP] Possible fixes:")
    print("       1. Check that you've added all required scopes")
    print("       2. Reinstall the app to workspace")
    print("       3. Make sure the token starts with 'xoxb-' (bot token) or 'xoxp-' (user token)")
    exit(1)
except Exception as e:
    print(f"\n[ERROR] Unexpected error: {str(e)}")
    exit(1)
