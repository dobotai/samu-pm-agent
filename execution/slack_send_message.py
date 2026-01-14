#!/usr/bin/env python3
"""
Slack Send Message Tool - Sends messages to Slack channels or users
Part of DOEBI execution layer (deterministic tool)

Usage:
    python slack_send_message.py <channel_or_user> <message> [--thread-ts <timestamp>]

Examples:
    python slack_send_message.py "#project-manager" "Checked in for the day"
    python slack_send_message.py "@U071040RR8S" "Hey, video #1360 is assigned to you"
    python slack_send_message.py "C071NUME7EC" "First draft looks great!"
    python slack_send_message.py "#general" "Follow up message" --thread-ts "1234567890.123456"
"""

import os
import sys
import json
import argparse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def send_slack_message(channel_or_user, message, thread_ts=None):
    """
    Send a message to a Slack channel or user

    Args:
        channel_or_user: Channel ID (C...), channel name (#channel), user ID (U...), or @username
        message: Message text to send
        thread_ts: Optional thread timestamp to reply in a thread

    Returns:
        Response with message timestamp and channel
    """
    # Get user token from environment (for full channel access)
    user_token = os.getenv('SLACK_USER_TOKEN')
    if not user_token:
        # Fallback to bot token if user token not available
        user_token = os.getenv('SLACK_BOT_TOKEN')
        if not user_token:
            raise ValueError("Neither SLACK_USER_TOKEN nor SLACK_BOT_TOKEN found in environment variables")

    # Initialize Slack client
    client = WebClient(token=user_token)

    # Handle different input formats
    channel = channel_or_user

    # If it starts with @, we need to look up the user ID and open a DM
    if channel.startswith('@'):
        username = channel[1:]  # Remove @
        # Look up user by username/display name
        try:
            # Try to find user by display name or real name
            users = client.users_list()
            user_id = None
            for user in users['members']:
                if (user.get('name') == username or
                    user.get('profile', {}).get('display_name') == username or
                    user.get('profile', {}).get('real_name') == username):
                    user_id = user['id']
                    break

            if not user_id:
                # If username looks like a user ID already, use it
                if username.startswith('U'):
                    user_id = username
                else:
                    raise ValueError(f"Could not find user: {username}")

            # Open a DM channel
            response = client.conversations_open(users=[user_id])
            channel = response['channel']['id']
        except SlackApiError as e:
            raise ValueError(f"Error opening DM with {username}: {e.response['error']}")

    # If it starts with #, remove it (Slack API doesn't need it)
    elif channel.startswith('#'):
        channel = channel[1:]

    # Send the message
    try:
        kwargs = {
            'channel': channel,
            'text': message
        }

        if thread_ts:
            kwargs['thread_ts'] = thread_ts

        response = client.chat_postMessage(**kwargs)

        return {
            'ok': True,
            'channel': response['channel'],
            'ts': response['ts'],
            'message': message
        }
    except SlackApiError as e:
        raise Exception(f"Error sending message: {e.response['error']}")

def main():
    parser = argparse.ArgumentParser(
        description='Send a message to a Slack channel or user',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "#project-manager" "Checked in for the day"
  %(prog)s "@ananda" "Hey, video #1360 is assigned to you"
  %(prog)s "C071NUME7EC" "First draft looks great!"
  %(prog)s "#general" "Follow up" --thread-ts "1234567890.123456"
        """
    )

    parser.add_argument('channel_or_user',
                       help='Channel (#channel or ID), or user (@username or ID)')
    parser.add_argument('message', help='Message text to send')
    parser.add_argument('--thread-ts', help='Thread timestamp to reply in thread')

    args = parser.parse_args()

    try:
        result = send_slack_message(
            channel_or_user=args.channel_or_user,
            message=args.message,
            thread_ts=args.thread_ts
        )

        print(json.dumps(result, indent=2))
        print(f"\nSuccess! Message sent to {result['channel']}", file=sys.stderr)

        return 0

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
