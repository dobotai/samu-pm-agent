#!/usr/bin/env python3
"""
Project Management Analytics Tool
Unified tool for project management queries combining Airtable and Slack data.

Supports:
- ETAs for projects / video completion estimates
- Unfollowed messages tracking
- Delayed deadline tracking
- Missed chats needing immediate attention
- Client/Editor specific message filtering
- Untended client messages
- Urgent tasks aggregation
- QC and checklist functionality
- End of day checklist
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Find the project root (parent of execution/tools)
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


class PMAnalytics:
    """Project Management Analytics combining Airtable and Slack data."""

    def __init__(self):
        # Slack setup
        self.slack_token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
        if not self.slack_token:
            raise ValueError("SLACK_USER_TOKEN or SLACK_BOT_TOKEN required")
        self.slack_client = WebClient(token=self.slack_token)

        # Airtable setup
        self.airtable_api_key = os.getenv("AIRTABLE_API_KEY")
        self.airtable_base_id = os.getenv("AIRTABLE_BASE_ID")
        if not self.airtable_api_key:
            raise ValueError("AIRTABLE_API_KEY required")

        self.airtable_headers = {
            "Authorization": f"Bearer {self.airtable_api_key}",
            "Content-Type": "application/json"
        }

        # Cache for Slack users
        self._user_cache = {}

    # ==========================================================================
    # SLACK HELPERS
    # ==========================================================================

    def _get_slack_user(self, user_id: str) -> Dict[str, Any]:
        """Get user info with caching."""
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            response = self.slack_client.users_info(user=user_id)
            user = response["user"]
            self._user_cache[user_id] = {
                "id": user_id,
                "name": user.get("real_name", user.get("name", "Unknown")),
                "email": user.get("profile", {}).get("email", ""),
                "is_bot": user.get("is_bot", False)
            }
        except:
            self._user_cache[user_id] = {
                "id": user_id,
                "name": "Unknown",
                "email": "",
                "is_bot": False
            }

        return self._user_cache[user_id]

    def _get_all_channels(self) -> List[Dict]:
        """Get all channels in workspace."""
        try:
            result = self.slack_client.conversations_list(
                types="public_channel,private_channel"
            )
            return result.get("channels", [])
        except SlackApiError:
            return []

    def _get_channel_messages(self, channel_id: str, limit: int = 100,
                               oldest: Optional[float] = None) -> List[Dict]:
        """Get messages from a channel."""
        try:
            kwargs = {"channel": channel_id, "limit": limit}
            if oldest:
                kwargs["oldest"] = str(oldest)

            result = self.slack_client.conversations_history(**kwargs)
            messages = []

            for msg in result.get("messages", []):
                user_info = self._get_slack_user(msg.get("user", "unknown"))
                ts = float(msg.get("ts", 0))
                dt = datetime.fromtimestamp(ts)

                messages.append({
                    "text": msg.get("text", ""),
                    "user_id": msg.get("user", "unknown"),
                    "user_name": user_info["name"],
                    "user_email": user_info["email"],
                    "timestamp": msg.get("ts"),
                    "datetime": dt.isoformat(),
                    "thread_ts": msg.get("thread_ts"),
                    "reply_count": msg.get("reply_count", 0),
                    "reactions": msg.get("reactions", []),
                    "channel_id": channel_id
                })

            return messages
        except SlackApiError as e:
            return []

    def _get_thread_replies(self, channel_id: str, thread_ts: str) -> List[Dict]:
        """Get replies to a thread."""
        try:
            result = self.slack_client.conversations_replies(
                channel=channel_id,
                ts=thread_ts
            )
            return result.get("messages", [])[1:]  # Skip parent message
        except SlackApiError:
            return []

    def _get_all_users(self) -> List[Dict]:
        """Get all workspace users."""
        try:
            result = self.slack_client.users_list()
            users = []
            for user in result.get("members", []):
                if not user.get("deleted", False) and not user.get("is_bot", False):
                    users.append({
                        "id": user["id"],
                        "name": user.get("real_name", user.get("name", "Unknown")),
                        "email": user.get("profile", {}).get("email", ""),
                        "is_bot": user.get("is_bot", False)
                    })
            return users
        except SlackApiError:
            return []

    # ==========================================================================
    # AIRTABLE HELPERS
    # ==========================================================================

    def _airtable_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make Airtable API request."""
        url = f"https://api.airtable.com/v0/{endpoint}"
        response = requests.get(url, headers=self.airtable_headers, params=params or {})
        response.raise_for_status()
        return response.json()

    def _get_airtable_records(self, table_name: str, filter_formula: str = None,
                               max_records: int = 100) -> List[Dict]:
        """Get records from Airtable table."""
        if not self.airtable_base_id:
            return []

        params = {"maxRecords": max_records}
        if filter_formula:
            params["filterByFormula"] = filter_formula

        try:
            data = self._airtable_request(
                f"{self.airtable_base_id}/{table_name}",
                params
            )
            return [
                {
                    "id": r["id"],
                    "fields": r.get("fields", {}),
                    "created_time": r.get("createdTime", "")
                }
                for r in data.get("records", [])
            ]
        except Exception as e:
            return []

    # ==========================================================================
    # ANALYTICS FUNCTIONS
    # ==========================================================================

    def get_project_etas(self, table_name: str = "Videos") -> Dict:
        """
        Get ETAs for all projects/videos.
        Returns projects with their deadlines and estimated completion.

        Question: "We need a video ASAP -> When will a video be ready?"
        """
        # Get tasks from Airtable
        records = self._get_airtable_records(table_name)

        projects = []
        for record in records:
            fields = record["fields"]

            # Common field name variations for deadline/due date
            deadline = (
                fields.get("Deadline") or
                fields.get("Due Date") or
                fields.get("Due") or
                fields.get("ETA") or
                fields.get("Expected Completion") or
                fields.get("Thumbnail Deadline") or
                None
            )

            # Video-specific status field
            status = (
                fields.get("Editing Status") or
                fields.get("Status") or
                fields.get("Stage") or
                fields.get("State") or
                fields.get("Thumbnail Status") or
                "Unknown"
            )

            # Video ID or name
            video_id = fields.get("Video ID")
            name = (
                fields.get("Name") or
                fields.get("Title") or
                fields.get("Project") or
                fields.get("Video") or
                fields.get("Task") or
                (f"Video #{video_id}" if video_id else None) or
                "Unnamed"
            )

            # Editor/Assignee - handle linked records
            editor_name = fields.get("Editor's Name")
            if isinstance(editor_name, list):
                editor_name = editor_name[0] if editor_name else None

            assignee = (
                editor_name or
                fields.get("Assignee") or
                fields.get("Assigned To") or
                fields.get("Owner") or
                fields.get("Assigned Editor") or
                None
            )

            # Client info
            client = fields.get("Client")

            projects.append({
                "id": record["id"],
                "name": name,
                "video_id": video_id,
                "status": status,
                "deadline": deadline,
                "assignee": assignee,
                "client": client,
                "all_fields": fields
            })

        # Sort by deadline (soonest first)
        projects_with_deadline = [p for p in projects if p["deadline"]]
        projects_without_deadline = [p for p in projects if not p["deadline"]]

        try:
            projects_with_deadline.sort(key=lambda x: x["deadline"])
        except:
            pass

        return {
            "projects": projects_with_deadline + projects_without_deadline,
            "count": len(projects),
            "with_deadline": len(projects_with_deadline),
            "without_deadline": len(projects_without_deadline)
        }

    def get_unfollowed_messages(self, hours: int = 24, channels: List[str] = None) -> Dict:
        """
        List all people who haven't followed up to messages.

        Question: "Messages get missed on slack. -> List all the people who
                   hasn't followed up to messages"
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_ts = cutoff.timestamp()

        all_channels = self._get_all_channels()
        if channels:
            # Filter to specific channels
            all_channels = [c for c in all_channels if c["name"] in channels or c["id"] in channels]

        unfollowed = []
        users_with_pending = {}

        for channel in all_channels:
            channel_id = channel["id"]
            channel_name = channel["name"]

            messages = self._get_channel_messages(channel_id, limit=100, oldest=cutoff_ts)

            for msg in messages:
                # Skip bot messages and messages without text
                if not msg["text"] or msg["user_id"] == "unknown":
                    continue

                # Check if this is a question or request that needs follow-up
                text_lower = msg["text"].lower()
                needs_followup = any([
                    "?" in msg["text"],
                    "@" in msg["text"],  # Mentions
                    "please" in text_lower,
                    "can you" in text_lower,
                    "could you" in text_lower,
                    "need" in text_lower,
                    "urgent" in text_lower,
                    "asap" in text_lower,
                ])

                if needs_followup:
                    # Check if there are replies
                    has_reply = False
                    if msg.get("thread_ts"):
                        replies = self._get_thread_replies(channel_id, msg["thread_ts"])
                        has_reply = len(replies) > 0
                    elif msg.get("reply_count", 0) > 0:
                        has_reply = True

                    # Check reactions as acknowledgment
                    has_reaction = len(msg.get("reactions", [])) > 0

                    if not has_reply and not has_reaction:
                        unfollowed.append({
                            "channel": channel_name,
                            "channel_id": channel_id,
                            "message": msg["text"][:200],
                            "from_user": msg["user_name"],
                            "from_user_id": msg["user_id"],
                            "timestamp": msg["timestamp"],
                            "datetime": msg["datetime"],
                            "thread_ts": msg.get("thread_ts")
                        })

                        # Track which users have pending messages
                        user_id = msg["user_id"]
                        if user_id not in users_with_pending:
                            users_with_pending[user_id] = {
                                "name": msg["user_name"],
                                "pending_count": 0
                            }
                        users_with_pending[user_id]["pending_count"] += 1

        return {
            "unfollowed_messages": unfollowed,
            "count": len(unfollowed),
            "users_with_pending": list(users_with_pending.values()),
            "time_range_hours": hours
        }

    def get_delayed_deadlines(self, table_name: str = "Videos") -> Dict:
        """
        Find tasks with missed deadlines that have no recent updates.

        Question: "Deadline not completed and delayed -> no update ->
                   forget delayed deadline"
        """
        records = self._get_airtable_records(table_name)
        today = datetime.now().date()

        delayed = []
        for record in records:
            fields = record["fields"]

            # Get deadline
            deadline_str = (
                fields.get("Deadline") or
                fields.get("Due Date") or
                fields.get("Due") or
                None
            )

            if not deadline_str:
                continue

            # Parse deadline
            try:
                if isinstance(deadline_str, str):
                    deadline = datetime.fromisoformat(deadline_str.replace("Z", "+00:00")).date()
                else:
                    continue
            except:
                continue

            # Check if deadline passed
            if deadline >= today:
                continue

            # Get status
            status = (
                fields.get("Status") or
                fields.get("Stage") or
                "Unknown"
            ).lower()

            # Skip completed tasks
            if status in ["done", "completed", "finished", "closed"]:
                continue

            # Get last modified or update info
            last_modified = (
                fields.get("Last Modified") or
                fields.get("Modified") or
                fields.get("Updated") or
                record.get("created_time") or
                None
            )

            days_overdue = (today - deadline).days

            name = (
                fields.get("Name") or
                fields.get("Title") or
                fields.get("Task") or
                "Unnamed"
            )

            assignee = (
                fields.get("Assignee") or
                fields.get("Assigned To") or
                fields.get("Owner") or
                None
            )

            delayed.append({
                "id": record["id"],
                "name": name,
                "status": status,
                "deadline": str(deadline),
                "days_overdue": days_overdue,
                "assignee": assignee,
                "last_modified": last_modified,
                "all_fields": fields
            })

        # Sort by days overdue (most overdue first)
        delayed.sort(key=lambda x: x["days_overdue"], reverse=True)

        return {
            "delayed_tasks": delayed,
            "count": len(delayed),
            "total_days_overdue": sum(d["days_overdue"] for d in delayed)
        }

    def get_attention_needed(self, hours: int = 24) -> Dict:
        """
        Find messages that need immediate attention.

        Question: "Is there anything that we've missed in chats that need
                   our immediate attention?"
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_ts = cutoff.timestamp()

        all_channels = self._get_all_channels()
        attention_needed = []

        urgent_keywords = [
            "urgent", "asap", "immediately", "emergency", "critical",
            "blocker", "blocked", "help", "issue", "problem", "broken",
            "down", "error", "failed", "failing", "not working"
        ]

        for channel in all_channels:
            channel_id = channel["id"]
            channel_name = channel["name"]

            messages = self._get_channel_messages(channel_id, limit=100, oldest=cutoff_ts)

            for msg in messages:
                if not msg["text"]:
                    continue

                text_lower = msg["text"].lower()

                # Check urgency indicators
                is_urgent = any(kw in text_lower for kw in urgent_keywords)
                has_mention = "@" in msg["text"]
                is_question = "?" in msg["text"]

                # Check if unacknowledged
                has_reply = msg.get("reply_count", 0) > 0
                has_reaction = len(msg.get("reactions", [])) > 0
                is_unacknowledged = not has_reply and not has_reaction

                # Prioritize urgent unacknowledged messages
                if is_urgent and is_unacknowledged:
                    priority = "high"
                elif (is_urgent or (has_mention and is_question)) and is_unacknowledged:
                    priority = "medium"
                elif is_unacknowledged and (is_question or has_mention):
                    priority = "low"
                else:
                    continue

                attention_needed.append({
                    "channel": channel_name,
                    "channel_id": channel_id,
                    "message": msg["text"][:300],
                    "from_user": msg["user_name"],
                    "datetime": msg["datetime"],
                    "priority": priority,
                    "is_urgent": is_urgent,
                    "has_mention": has_mention,
                    "is_question": is_question,
                    "timestamp": msg["timestamp"]
                })

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        attention_needed.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return {
            "attention_needed": attention_needed,
            "count": len(attention_needed),
            "high_priority": len([a for a in attention_needed if a["priority"] == "high"]),
            "medium_priority": len([a for a in attention_needed if a["priority"] == "medium"]),
            "low_priority": len([a for a in attention_needed if a["priority"] == "low"]),
            "time_range_hours": hours
        }

    def get_client_messages(self, hours: int = 24, tended: bool = False) -> Dict:
        """
        Get client-specific messages, optionally filtering for untended ones.

        Questions:
        - "Specifically for clients"
        - "Are there any client messages that have not be tended to? within the day"
        - "Check within the last day and see client messages that have not been tended to"
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_ts = cutoff.timestamp()

        all_channels = self._get_all_channels()

        # Find client channels (common naming patterns)
        client_patterns = ["client", "customer", "-c-", "_c_"]
        client_channels = []

        for channel in all_channels:
            name_lower = channel["name"].lower()
            if any(p in name_lower for p in client_patterns):
                client_channels.append(channel)

        # If no client channels found by pattern, return all channels
        if not client_channels:
            client_channels = all_channels

        messages = []
        for channel in client_channels:
            channel_id = channel["id"]
            channel_name = channel["name"]

            channel_messages = self._get_channel_messages(channel_id, limit=100, oldest=cutoff_ts)

            for msg in channel_messages:
                if not msg["text"]:
                    continue

                has_reply = msg.get("reply_count", 0) > 0
                has_reaction = len(msg.get("reactions", [])) > 0
                is_tended = has_reply or has_reaction

                # Filter based on tended parameter
                if tended and not is_tended:
                    continue
                if not tended and is_tended:
                    continue

                messages.append({
                    "channel": channel_name,
                    "channel_id": channel_id,
                    "message": msg["text"][:300],
                    "from_user": msg["user_name"],
                    "datetime": msg["datetime"],
                    "is_tended": is_tended,
                    "has_reply": has_reply,
                    "has_reaction": has_reaction,
                    "timestamp": msg["timestamp"]
                })

        return {
            "messages": messages,
            "count": len(messages),
            "channels_checked": [c["name"] for c in client_channels],
            "time_range_hours": hours,
            "filter": "tended" if tended else "untended"
        }

    def get_editor_messages(self, hours: int = 24, tended: bool = False) -> Dict:
        """
        Get editor-specific messages.

        Question: "Specifically for editors"
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_ts = cutoff.timestamp()

        all_channels = self._get_all_channels()

        # Find editor channels (common naming patterns)
        editor_patterns = ["editor", "edit", "-e-", "_e_", "post-production", "postprod"]
        editor_channels = []

        for channel in all_channels:
            name_lower = channel["name"].lower()
            if any(p in name_lower for p in editor_patterns):
                editor_channels.append(channel)

        messages = []
        for channel in editor_channels:
            channel_id = channel["id"]
            channel_name = channel["name"]

            channel_messages = self._get_channel_messages(channel_id, limit=100, oldest=cutoff_ts)

            for msg in channel_messages:
                if not msg["text"]:
                    continue

                has_reply = msg.get("reply_count", 0) > 0
                has_reaction = len(msg.get("reactions", [])) > 0
                is_tended = has_reply or has_reaction

                if tended and not is_tended:
                    continue
                if not tended and is_tended:
                    continue

                messages.append({
                    "channel": channel_name,
                    "channel_id": channel_id,
                    "message": msg["text"][:300],
                    "from_user": msg["user_name"],
                    "datetime": msg["datetime"],
                    "is_tended": is_tended,
                    "timestamp": msg["timestamp"]
                })

        return {
            "messages": messages,
            "count": len(messages),
            "channels_checked": [c["name"] for c in editor_channels],
            "time_range_hours": hours,
            "filter": "tended" if tended else "untended"
        }

    def get_urgent_tasks_today(self, table_name: str = "Videos") -> Dict:
        """
        Generate list of all tasks that need to be completed today based on urgency.

        Question: "Generate me a list of all tasks that need to be completed
                   today based off urgency (using both airtable and slack as context)"
        """
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        # Get Airtable tasks
        records = self._get_airtable_records(table_name)

        urgent_tasks = []
        for record in records:
            fields = record["fields"]

            # Get deadline
            deadline_str = (
                fields.get("Deadline") or
                fields.get("Due Date") or
                fields.get("Due") or
                None
            )

            status = (
                fields.get("Status") or
                fields.get("Stage") or
                "Unknown"
            ).lower()

            # Skip completed
            if status in ["done", "completed", "finished", "closed"]:
                continue

            # Get priority
            priority = (
                fields.get("Priority") or
                fields.get("Urgency") or
                "normal"
            )

            name = (
                fields.get("Name") or
                fields.get("Title") or
                fields.get("Task") or
                "Unnamed"
            )

            assignee = (
                fields.get("Assignee") or
                fields.get("Assigned To") or
                None
            )

            # Determine urgency
            urgency_score = 0

            # Check deadline
            if deadline_str:
                try:
                    if isinstance(deadline_str, str):
                        deadline = datetime.fromisoformat(deadline_str.replace("Z", "+00:00")).date()
                        if deadline < today:
                            urgency_score += 10  # Overdue
                        elif deadline == today:
                            urgency_score += 8  # Due today
                        elif deadline == tomorrow:
                            urgency_score += 5  # Due tomorrow
                except:
                    pass

            # Check priority field
            priority_lower = str(priority).lower()
            if priority_lower in ["high", "urgent", "critical"]:
                urgency_score += 5
            elif priority_lower == "medium":
                urgency_score += 2

            # Check status
            if "blocked" in status or "waiting" in status:
                urgency_score += 3

            if urgency_score > 0:
                urgent_tasks.append({
                    "id": record["id"],
                    "name": name,
                    "status": status,
                    "priority": priority,
                    "deadline": deadline_str,
                    "assignee": assignee,
                    "urgency_score": urgency_score,
                    "source": "airtable"
                })

        # Get urgent messages from Slack
        cutoff = datetime.now() - timedelta(hours=24)
        cutoff_ts = cutoff.timestamp()

        all_channels = self._get_all_channels()
        urgent_keywords = ["urgent", "asap", "today", "eod", "end of day", "immediately"]

        for channel in all_channels:
            channel_id = channel["id"]
            channel_name = channel["name"]

            messages = self._get_channel_messages(channel_id, limit=50, oldest=cutoff_ts)

            for msg in messages:
                if not msg["text"]:
                    continue

                text_lower = msg["text"].lower()

                if any(kw in text_lower for kw in urgent_keywords):
                    # Check if unacknowledged
                    has_reply = msg.get("reply_count", 0) > 0
                    has_reaction = len(msg.get("reactions", [])) > 0

                    if not has_reply and not has_reaction:
                        urgent_tasks.append({
                            "name": f"[Slack] {msg['text'][:100]}",
                            "channel": channel_name,
                            "from_user": msg["user_name"],
                            "datetime": msg["datetime"],
                            "urgency_score": 7,
                            "source": "slack",
                            "timestamp": msg["timestamp"]
                        })

        # Sort by urgency score
        urgent_tasks.sort(key=lambda x: x["urgency_score"], reverse=True)

        return {
            "urgent_tasks": urgent_tasks,
            "count": len(urgent_tasks),
            "from_airtable": len([t for t in urgent_tasks if t.get("source") == "airtable"]),
            "from_slack": len([t for t in urgent_tasks if t.get("source") == "slack"])
        }

    def get_qc_checklist(self, table_name: str = "Videos") -> Dict:
        """
        Get QC/Quality check items and status.

        Question: "QCs/Checking with clients/Checking with editors"
        """
        # Get tasks that need QC
        records = self._get_airtable_records(table_name)

        qc_items = []
        client_checks = []
        editor_checks = []

        for record in records:
            fields = record["fields"]

            # Get editing and thumbnail status for video tables
            editing_status = (
                fields.get("Editing Status") or
                fields.get("Status") or
                fields.get("Stage") or
                ""
            ).lower()

            thumbnail_status = (
                fields.get("Thumbnail Status") or
                ""
            ).lower()

            # Combine statuses for checking
            combined_status = f"{editing_status} {thumbnail_status}"

            # Get video name
            video_id = fields.get("Video ID")
            name = (
                fields.get("Name") or
                fields.get("Title") or
                (f"Video #{video_id}" if video_id else None) or
                "Unnamed"
            )

            # Get editor info
            editor_name = fields.get("Editor's Name")
            if isinstance(editor_name, list):
                editor_name = editor_name[0] if editor_name else None

            # QC items - videos needing quality check
            qc_keywords = ["qc", "review", "check", "internal"]
            if any(kw in combined_status for kw in qc_keywords):
                qc_items.append({
                    "id": record["id"],
                    "name": name,
                    "editing_status": editing_status,
                    "thumbnail_status": thumbnail_status,
                    "editor": editor_name,
                    "fields": fields
                })

            # Client checks - videos waiting for client approval/feedback
            client_keywords = ["client", "approval", "feedback", "waiting", "sent"]
            if any(kw in combined_status for kw in client_keywords):
                client_checks.append({
                    "id": record["id"],
                    "name": name,
                    "editing_status": editing_status,
                    "thumbnail_status": thumbnail_status,
                    "editor": editor_name,
                    "fields": fields
                })

            # Editor checks - videos in editing stages
            editor_keywords = ["edit", "revision", "draft", "rough", "first"]
            is_not_done = "done" not in editing_status and "scheduled" not in editing_status
            if any(kw in combined_status for kw in editor_keywords) or (is_not_done and editor_name):
                editor_checks.append({
                    "id": record["id"],
                    "name": name,
                    "editing_status": editing_status,
                    "thumbnail_status": thumbnail_status,
                    "editor": editor_name,
                    "fields": fields
                })

        return {
            "qc_items": qc_items,
            "qc_count": len(qc_items),
            "client_checks": client_checks,
            "client_check_count": len(client_checks),
            "editor_checks": editor_checks,
            "editor_check_count": len(editor_checks)
        }

    def get_end_of_day_checklist(self, table_name: str = "Videos") -> Dict:
        """
        Generate end of day checklist combining all checks.

        Question: "End of day checklist"
        """
        today = datetime.now().date()

        # Get all the analytics
        etas = self.get_project_etas(table_name)
        unfollowed = self.get_unfollowed_messages(hours=24)
        delayed = self.get_delayed_deadlines(table_name)
        attention = self.get_attention_needed(hours=24)
        client_untended = self.get_client_messages(hours=24, tended=False)
        editor_untended = self.get_editor_messages(hours=24, tended=False)
        urgent = self.get_urgent_tasks_today(table_name)
        qc = self.get_qc_checklist(table_name)

        # Build checklist
        checklist = {
            "date": str(today),
            "summary": {
                "total_projects": etas["count"],
                "projects_with_deadlines": etas["with_deadline"],
                "unfollowed_messages": unfollowed["count"],
                "delayed_tasks": delayed["count"],
                "attention_needed": attention["count"],
                "untended_client_messages": client_untended["count"],
                "untended_editor_messages": editor_untended["count"],
                "urgent_tasks": urgent["count"],
                "qc_pending": qc["qc_count"],
                "client_checks_pending": qc["client_check_count"],
                "editor_checks_pending": qc["editor_check_count"]
            },
            "action_items": []
        }

        # Add high priority items to action items
        if attention["high_priority"] > 0:
            checklist["action_items"].append({
                "priority": "HIGH",
                "type": "immediate_attention",
                "count": attention["high_priority"],
                "description": f"{attention['high_priority']} messages need immediate attention"
            })

        if delayed["count"] > 0:
            checklist["action_items"].append({
                "priority": "HIGH",
                "type": "delayed_deadlines",
                "count": delayed["count"],
                "description": f"{delayed['count']} tasks are past their deadline"
            })

        if client_untended["count"] > 0:
            checklist["action_items"].append({
                "priority": "MEDIUM",
                "type": "client_messages",
                "count": client_untended["count"],
                "description": f"{client_untended['count']} client messages haven't been addressed"
            })

        if unfollowed["count"] > 0:
            checklist["action_items"].append({
                "priority": "MEDIUM",
                "type": "unfollowed_messages",
                "count": unfollowed["count"],
                "description": f"{unfollowed['count']} messages are awaiting follow-up"
            })

        if qc["qc_count"] > 0:
            checklist["action_items"].append({
                "priority": "MEDIUM",
                "type": "qc_pending",
                "count": qc["qc_count"],
                "description": f"{qc['qc_count']} items pending QC"
            })

        # Add detailed data
        checklist["details"] = {
            "attention_needed": attention["attention_needed"][:10],
            "delayed_tasks": delayed["delayed_tasks"][:10],
            "unfollowed_messages": unfollowed["unfollowed_messages"][:10],
            "untended_client_messages": client_untended["messages"][:10],
            "urgent_tasks": urgent["urgent_tasks"][:10]
        }

        return checklist


def main():
    """CLI interface for PM Analytics."""
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action parameter",
            "available_actions": [
                "get_project_etas",
                "get_unfollowed_messages",
                "get_delayed_deadlines",
                "get_attention_needed",
                "get_client_messages",
                "get_editor_messages",
                "get_urgent_tasks_today",
                "get_qc_checklist",
                "get_end_of_day_checklist"
            ]
        }))
        sys.exit(1)

    action = sys.argv[1]

    # Parse optional params
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            # Fallback for simple args
            params = {}

    try:
        analytics = PMAnalytics()

        if action == "get_project_etas":
            table_name = params.get("table_name", "Videos")
            result = analytics.get_project_etas(table_name)

        elif action == "get_unfollowed_messages":
            hours = params.get("hours", 24)
            channels = params.get("channels")
            result = analytics.get_unfollowed_messages(hours, channels)

        elif action == "get_delayed_deadlines":
            table_name = params.get("table_name", "Videos")
            result = analytics.get_delayed_deadlines(table_name)

        elif action == "get_attention_needed":
            hours = params.get("hours", 24)
            result = analytics.get_attention_needed(hours)

        elif action == "get_client_messages":
            hours = params.get("hours", 24)
            tended = params.get("tended", False)
            result = analytics.get_client_messages(hours, tended)

        elif action == "get_editor_messages":
            hours = params.get("hours", 24)
            tended = params.get("tended", False)
            result = analytics.get_editor_messages(hours, tended)

        elif action == "get_urgent_tasks_today":
            table_name = params.get("table_name", "Videos")
            result = analytics.get_urgent_tasks_today(table_name)

        elif action == "get_qc_checklist":
            table_name = params.get("table_name", "Videos")
            result = analytics.get_qc_checklist(table_name)

        elif action == "get_end_of_day_checklist":
            table_name = params.get("table_name", "Videos")
            result = analytics.get_end_of_day_checklist(table_name)

        else:
            print(json.dumps({
                "error": f"Unknown action: {action}",
                "available_actions": [
                    "get_project_etas",
                    "get_unfollowed_messages",
                    "get_delayed_deadlines",
                    "get_attention_needed",
                    "get_client_messages",
                    "get_editor_messages",
                    "get_urgent_tasks_today",
                    "get_qc_checklist",
                    "get_end_of_day_checklist"
                ]
            }))
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))

    except Exception as e:
        print(json.dumps({
            "error": str(e)
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
