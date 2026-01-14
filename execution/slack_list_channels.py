#!/usr/bin/env python3
"""
Slack List Channels Tool - Lists all Slack channels (editors and clients)
Part of DOEBI execution layer (deterministic tool)

Usage:
    python slack_list_channels.py [--filter <pattern>] [--types <types>]

Examples:
    python slack_list_channels.py
    python slack_list_channels.py --filter "editor"
    python slack_list_channels.py --filter "client" --types "public_channel,private_channel"
"""

import os
import sys
import json
import argparse
import re
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def list_slack_channels(filter_pattern=None, types='public_channel,private_channel'):
    """
    List all Slack channels

    Args:
        filter_pattern: Optional regex pattern to filter channel names
        types: Comma-separated list of channel types

    Returns:
        List of channels with metadata
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

    try:
        # Fetch all channels
        response = client.conversations_list(
            types=types,
            limit=1000
        )

        channels = response['channels']

        # Apply filter if specified
        if filter_pattern:
            pattern = re.compile(filter_pattern, re.IGNORECASE)
            channels = [ch for ch in channels if pattern.search(ch['name'])]

        # Format channel data
        formatted_channels = []
        for ch in channels:
            formatted_channels.append({
                'id': ch['id'],
                'name': ch['name'],
                'is_private': ch.get('is_private', False),
                'is_channel': ch.get('is_channel', True),
                'is_archived': ch.get('is_archived', False),
                'num_members': ch.get('num_members', 0),
                'topic': ch.get('topic', {}).get('value', ''),
                'purpose': ch.get('purpose', {}).get('value', '')
            })

        return formatted_channels

    except SlackApiError as e:
        raise Exception(f"Error listing channels: {e.response['error']}")

def main():
    parser = argparse.ArgumentParser(
        description='List all Slack channels',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --filter "editor"
  %(prog)s --filter "client" --types "public_channel,private_channel"
        """
    )

    parser.add_argument('--filter', dest='filter_pattern',
                       help='Regex pattern to filter channel names')
    parser.add_argument('--types', default='public_channel,private_channel',
                       help='Channel types to include (default: public and private)')
    parser.add_argument('--output', choices=['json', 'summary'], default='summary',
                       help='Output format (default: summary)')

    args = parser.parse_args()

    try:
        channels = list_slack_channels(
            filter_pattern=args.filter_pattern,
            types=args.types
        )

        if args.output == 'json':
            print(json.dumps(channels, indent=2))
        else:
            # Summary output
            print(f"Found {len(channels)} channels\n")

            # Categorize channels
            editor_channels = [ch for ch in channels if 'editor' in ch['name'].lower()]
            client_channels = [ch for ch in channels if 'client' not in ch['name'].lower() and 'editor' not in ch['name'].lower() and ch['name'] not in ['general', 'project-manager', 'random']]
            other_channels = [ch for ch in channels if ch not in editor_channels and ch not in client_channels]

            if editor_channels:
                print("=== EDITOR CHANNELS ===")
                for ch in editor_channels:
                    privacy = "[PRIVATE]" if ch['is_private'] else "[PUBLIC]"
                    print(f"{privacy} #{ch['name']} ({ch['id']}) - {ch['num_members']} members")
                print()

            if client_channels:
                print("=== CLIENT CHANNELS ===")
                for ch in client_channels:
                    privacy = "[PRIVATE]" if ch['is_private'] else "[PUBLIC]"
                    print(f"{privacy} #{ch['name']} ({ch['id']}) - {ch['num_members']} members")
                print()

            if other_channels:
                print("=== OTHER CHANNELS ===")
                for ch in other_channels:
                    privacy = "[PRIVATE]" if ch['is_private'] else "[PUBLIC]"
                    print(f"{privacy} #{ch['name']} ({ch['id']}) - {ch['num_members']} members")
                print()

        return 0

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
