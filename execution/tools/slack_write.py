#!/usr/bin/env python3
"""
Slack Write Tool
Send messages, create channels, manage conversations
"""

import json
import os
import sys
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def main():
    """Write operations to Slack workspace"""

    # Get Slack token from environment (prefer User Token for full access)
    slack_token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
    if not slack_token:
        print(json.dumps({
            "error": "SLACK_USER_TOKEN or SLACK_BOT_TOKEN not found in environment variables"
        }))
        sys.exit(1)

    # Parse input arguments
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action parameter. Usage: slack_write.py <action> [params]"
        }))
        sys.exit(1)

    action = sys.argv[1]
    client = WebClient(token=slack_token)

    try:
        if action == "send_message":
            # Send a message to a channel or user
            if len(sys.argv) < 4:
                print(json.dumps({
                    "error": "Missing parameters. Usage: slack_write.py send_message <channel_id_or_user> <message>"
                }))
                sys.exit(1)

            channel = sys.argv[2]
            message = sys.argv[3]

            result = client.chat_postMessage(
                channel=channel,
                text=message
            )

            print(json.dumps({
                "success": True,
                "message": "Message sent successfully",
                "channel": result["channel"],
                "timestamp": result["ts"],
                "message_text": message
            }))

        elif action == "send_dm":
            # Send a direct message to a user
            if len(sys.argv) < 4:
                print(json.dumps({
                    "error": "Missing parameters. Usage: slack_write.py send_dm <user_id_or_email> <message>"
                }))
                sys.exit(1)

            user_identifier = sys.argv[2]
            message = sys.argv[3]

            # If identifier looks like an email, look up user ID
            if "@" in user_identifier:
                user_result = client.users_lookupByEmail(email=user_identifier)
                user_id = user_result["user"]["id"]
            else:
                user_id = user_identifier

            # Open a DM conversation
            dm_result = client.conversations_open(users=[user_id])
            dm_channel = dm_result["channel"]["id"]

            # Send the message
            result = client.chat_postMessage(
                channel=dm_channel,
                text=message
            )

            print(json.dumps({
                "success": True,
                "message": "Direct message sent successfully",
                "user_id": user_id,
                "timestamp": result["ts"],
                "message_text": message
            }))

        elif action == "reply_to_thread":
            # Reply to a message thread
            if len(sys.argv) < 5:
                print(json.dumps({
                    "error": "Missing parameters. Usage: slack_write.py reply_to_thread <channel_id> <thread_ts> <message>"
                }))
                sys.exit(1)

            channel = sys.argv[2]
            thread_ts = sys.argv[3]
            message = sys.argv[4]

            result = client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=message
            )

            print(json.dumps({
                "success": True,
                "message": "Reply sent successfully",
                "channel": result["channel"],
                "timestamp": result["ts"],
                "thread_ts": thread_ts,
                "message_text": message
            }))

        elif action == "update_message":
            # Update an existing message
            if len(sys.argv) < 5:
                print(json.dumps({
                    "error": "Missing parameters. Usage: slack_write.py update_message <channel_id> <message_ts> <new_message>"
                }))
                sys.exit(1)

            channel = sys.argv[2]
            ts = sys.argv[3]
            new_message = sys.argv[4]

            result = client.chat_update(
                channel=channel,
                ts=ts,
                text=new_message
            )

            print(json.dumps({
                "success": True,
                "message": "Message updated successfully",
                "channel": result["channel"],
                "timestamp": result["ts"],
                "new_text": new_message
            }))

        elif action == "add_reaction":
            # Add an emoji reaction to a message
            if len(sys.argv) < 5:
                print(json.dumps({
                    "error": "Missing parameters. Usage: slack_write.py add_reaction <channel_id> <message_ts> <emoji_name>"
                }))
                sys.exit(1)

            channel = sys.argv[2]
            timestamp = sys.argv[3]
            emoji = sys.argv[4].strip(":")  # Remove colons if provided

            client.reactions_add(
                channel=channel,
                timestamp=timestamp,
                name=emoji
            )

            print(json.dumps({
                "success": True,
                "message": f"Reaction :{emoji}: added successfully",
                "channel": channel,
                "timestamp": timestamp
            }))

        elif action == "set_channel_topic":
            # Set the topic for a channel
            if len(sys.argv) < 4:
                print(json.dumps({
                    "error": "Missing parameters. Usage: slack_write.py set_channel_topic <channel_id> <topic>"
                }))
                sys.exit(1)

            channel = sys.argv[2]
            topic = sys.argv[3]

            result = client.conversations_setTopic(
                channel=channel,
                topic=topic
            )

            print(json.dumps({
                "success": True,
                "message": "Channel topic updated successfully",
                "channel": channel,
                "topic": topic
            }))

        elif action == "invite_to_channel":
            # Invite users to a channel
            if len(sys.argv) < 4:
                print(json.dumps({
                    "error": "Missing parameters. Usage: slack_write.py invite_to_channel <channel_id> <user_id>"
                }))
                sys.exit(1)

            channel = sys.argv[2]
            user_id = sys.argv[3]

            client.conversations_invite(
                channel=channel,
                users=[user_id]
            )

            print(json.dumps({
                "success": True,
                "message": "User invited to channel successfully",
                "channel": channel,
                "user_id": user_id
            }))

        elif action == "schedule_message":
            # Schedule a message for future delivery
            if len(sys.argv) < 5:
                print(json.dumps({
                    "error": "Missing parameters. Usage: slack_write.py schedule_message <channel_id> <unix_timestamp> <message>"
                }))
                sys.exit(1)

            channel = sys.argv[2]
            post_at = int(sys.argv[3])
            message = sys.argv[4]

            result = client.chat_scheduleMessage(
                channel=channel,
                post_at=post_at,
                text=message
            )

            print(json.dumps({
                "success": True,
                "message": "Message scheduled successfully",
                "channel": channel,
                "scheduled_message_id": result["scheduled_message_id"],
                "post_at": post_at,
                "message_text": message
            }))

        else:
            print(json.dumps({
                "error": f"Unknown action: {action}",
                "available_actions": [
                    "send_message",
                    "send_dm",
                    "reply_to_thread",
                    "update_message",
                    "add_reaction",
                    "set_channel_topic",
                    "invite_to_channel",
                    "schedule_message"
                ]
            }))
            sys.exit(1)

    except SlackApiError as e:
        print(json.dumps({
            "error": f"Slack API error: {e.response['error']}",
            "details": e.response.get("error", "")
        }))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "error": f"Unexpected error: {str(e)}"
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
