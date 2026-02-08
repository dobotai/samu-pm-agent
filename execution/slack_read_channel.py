#!/usr/bin/env python3
"""
Slack Read Channel Tool - Reads messages from a Slack channel
Part of DOEBI execution layer (deterministic tool)

Usage:
    python slack_read_channel.py <channel> [--limit <num>] [--since <hours>] [--no-threads]

Examples:
    python slack_read_channel.py "#project-manager"
    python slack_read_channel.py "C071NUME7EC" --limit 50
    python slack_read_channel.py "#editor-ananda" --since 24
    python slack_read_channel.py "#jamal-client" --since 48 --no-threads
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def read_slack_channel(channel, limit=100, since_hours=None, include_threads=True, max_threads=50):
    """
    Read messages from a Slack channel

    Args:
        channel: Channel ID (C...) or channel name (#channel)
        limit: Maximum number of messages to retrieve
        since_hours: Only get messages from last N hours
        include_threads: Fetch thread replies for messages with replies (default: True)
        max_threads: Maximum number of threads to fetch replies for (default: 50)

    Returns:
        List of messages with metadata (and thread_replies if include_threads=True)
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

    # Handle channel name format
    if channel.startswith('#'):
        channel_name = channel[1:]
        # Look up channel ID by name
        try:
            response = client.conversations_list(types='public_channel,private_channel')
            channel_id = None
            for ch in response['channels']:
                if ch['name'] == channel_name:
                    channel_id = ch['id']
                    break
            if not channel_id:
                raise ValueError(f"Could not find channel: {channel}")
            channel = channel_id
        except SlackApiError as e:
            raise ValueError(f"Error finding channel: {e.response['error']}")

    # Calculate oldest timestamp if since_hours is specified
    oldest = None
    if since_hours:
        oldest_dt = datetime.now() - timedelta(hours=since_hours)
        oldest = oldest_dt.timestamp()

    # Fetch messages
    try:
        kwargs = {
            'channel': channel,
            'limit': limit
        }
        if oldest:
            kwargs['oldest'] = str(oldest)

        response = client.conversations_history(**kwargs)
        messages = response['messages']

        # Get user info for message authors
        user_cache = {}

        formatted_messages = []
        for msg in messages:
            user_id = msg.get('user', 'unknown')

            # Get user info if we don't have it cached
            if user_id not in user_cache and user_id != 'unknown':
                try:
                    user_info = client.users_info(user=user_id)
                    user_cache[user_id] = {
                        'name': user_info['user'].get('real_name', 'Unknown'),
                        'username': user_info['user'].get('name', 'unknown')
                    }
                except:
                    user_cache[user_id] = {'name': 'Unknown', 'username': user_id}

            user_data = user_cache.get(user_id, {'name': 'Unknown', 'username': 'unknown'})

            # Format timestamp
            ts = float(msg.get('ts', 0))
            dt = datetime.fromtimestamp(ts)

            formatted_messages.append({
                'text': msg.get('text', ''),
                'user': user_data['name'],
                'username': user_data['username'],
                'user_id': user_id,
                'timestamp': msg.get('ts'),
                'datetime': dt.strftime('%Y-%m-%d %H:%M:%S'),
                'thread_ts': msg.get('thread_ts'),
                'reply_count': msg.get('reply_count', 0),
                'thread_replies': []
            })

        # Fetch thread replies for messages that have them
        if include_threads:
            threads_fetched = 0
            for fmt_msg, raw_msg in zip(formatted_messages, messages):
                if raw_msg.get('reply_count', 0) > 0 and threads_fetched < max_threads:
                    try:
                        thread_result = client.conversations_replies(
                            channel=channel,
                            ts=raw_msg['ts']
                        )
                        # Skip first message (it's the parent)
                        for reply in thread_result.get('messages', [])[1:]:
                            reply_user_id = reply.get('user', 'unknown')
                            if reply_user_id not in user_cache and reply_user_id != 'unknown':
                                try:
                                    reply_user_info = client.users_info(user=reply_user_id)
                                    user_cache[reply_user_id] = {
                                        'name': reply_user_info['user'].get('real_name', 'Unknown'),
                                        'username': reply_user_info['user'].get('name', 'unknown')
                                    }
                                except:
                                    user_cache[reply_user_id] = {'name': 'Unknown', 'username': reply_user_id}

                            reply_user_data = user_cache.get(reply_user_id, {'name': 'Unknown', 'username': 'unknown'})
                            reply_ts = float(reply.get('ts', 0))
                            reply_dt = datetime.fromtimestamp(reply_ts)

                            fmt_msg['thread_replies'].append({
                                'text': reply.get('text', ''),
                                'user': reply_user_data['name'],
                                'username': reply_user_data['username'],
                                'user_id': reply_user_id,
                                'timestamp': reply.get('ts'),
                                'datetime': reply_dt.strftime('%Y-%m-%d %H:%M:%S'),
                            })
                        threads_fetched += 1
                    except SlackApiError:
                        pass

        return formatted_messages

    except SlackApiError as e:
        raise Exception(f"Error reading channel: {e.response['error']}")

def main():
    parser = argparse.ArgumentParser(
        description='Read messages from a Slack channel',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "#project-manager"
  %(prog)s "C071NUME7EC" --limit 50
  %(prog)s "#editor-ananda" --since 24
        """
    )

    parser.add_argument('channel', help='Channel name (#channel) or ID (C...)')
    parser.add_argument('--limit', type=int, default=100,
                       help='Maximum number of messages to retrieve (default: 100)')
    parser.add_argument('--since', type=float, dest='since_hours',
                       help='Only get messages from last N hours')
    parser.add_argument('--no-threads', action='store_true', default=False,
                       help='Skip fetching thread replies (faster)')
    parser.add_argument('--output', choices=['json', 'summary'], default='json',
                       help='Output format (default: json)')

    args = parser.parse_args()

    try:
        messages = read_slack_channel(
            channel=args.channel,
            limit=args.limit,
            since_hours=args.since_hours,
            include_threads=not args.no_threads
        )

        if args.output == 'json':
            print(json.dumps(messages, indent=2))
        else:
            # Summary output
            total_thread_replies = sum(len(m.get('thread_replies', [])) for m in messages)
            print(f"Found {len(messages)} messages in {args.channel}")
            if total_thread_replies:
                print(f"  ({total_thread_replies} thread replies across {sum(1 for m in messages if m.get('thread_replies'))} threads)")
            print()
            for msg in messages[:10]:
                print(f"[{msg['datetime']}] {msg['user']}: {msg['text'][:100]}")
                if len(msg['text']) > 100:
                    print("...")
                for reply in msg.get('thread_replies', []):
                    print(f"  -> [{reply['datetime']}] {reply['user']}: {reply['text'][:100]}")
                print()
            if len(messages) > 10:
                print(f"... and {len(messages) - 10} more messages")

        return 0

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
