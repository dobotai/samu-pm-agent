#!/usr/bin/env python3
"""
Slack Task Scanner - LLM-Powered Task Extraction from Slack Messages

Uses Claude to intelligently scan Slack channels and extract ALL tasks, requests,
and action items from conversational messages. Goes far beyond keyword detection
to find casual requests, implied tasks, blockers, and follow-ups.

Cross-references with Airtable to show which tasks are already tracked vs. new/untracked.

Actions:
    extract_tasks  - Full scan: collect messages, LLM analysis, Airtable cross-reference
    scan_channel   - Scan a single channel only
    get_untracked  - Like extract_tasks but only returns tasks NOT in Airtable

Usage:
    python execution/tools/slack_task_scanner.py extract_tasks
    python execution/tools/slack_task_scanner.py extract_tasks '{"hours": 48}'
    python execution/tools/slack_task_scanner.py extract_tasks '{"hours": 24, "channels": ["raj-editing"]}'
    python execution/tools/slack_task_scanner.py extract_tasks '{"hours": 24, "dry_run": true}'
    python execution/tools/slack_task_scanner.py get_untracked '{"hours": 24}'
    python execution/tools/slack_task_scanner.py scan_channel '{"channel": "raj-editing", "hours": 48}'
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from anthropic import Anthropic
from pyairtable import Api


# Messages that are just acknowledgments (don't contain tasks)
ACKNOWLEDGMENT_PATTERNS = [
    r'^(ok|okay|k|kk)[\.\!]?$',
    r'^(thanks|thank you|thx|ty)[\.\!]?$',
    r'^(awesome|great|perfect|nice|cool|sounds good|got it|noted)[\.\!]?$',
    r'^(yes|yep|yup|yeah|yea)[\.\!]?$',
    r'^(no problem|np|no worries|nw)[\.\!]?$',
    r'^\:[\w\+\-]+\:$',
    r'^(will do|on it|doing it now)[\.\!]?$',
]

# Channel type classification patterns
EDITOR_CHANNEL_PATTERN = re.compile(r'-editing$')
CLIENT_CHANNEL_PATTERN = re.compile(r'-client$')
THUMBNAIL_CHANNEL_PATTERN = re.compile(r'thumbnail')
PM_CHANNEL_PATTERN = re.compile(r'project-manager')

TASK_EXTRACTION_PROMPT = """You are analyzing Slack messages from a YouTube video production agency. Your job is to identify ALL tasks, requests, action items, and obligations - even when stated casually or indirectly.

## Context
This agency produces YouTube videos for B2B SaaS clients. The team includes:
- Samu (Owner/Leadership) - makes strategic decisions, approves client comms
- Project Managers (PMs) who coordinate everything
- Editors who edit videos
- Ram (Thumbnail designer)
- Clients who provide recordings and feedback

## Channel: #{channel_name}
## Channel Type: {channel_type}

## Team Members
{team_members_block}

## Messages (chronological, most recent last):
{messages_block}

## Your Task
Extract EVERY task, request, or action item. Pay special attention to:

1. **Direct requests**: "can you do X", "please send", "make sure to", "need you to"
2. **Indirect/casual requests**: "when are you sending...", "can you check if...", "I need X by..."
3. **Implied tasks from questions**: "By when do you need these?" = someone needs to answer with a date
4. **Blockers needing PM action**: "I don't think I can finish this" = needs reassignment or timeline change
5. **Client requests**: anything a client asks for = task for the team
6. **Follow-up needed**: Questions without answers, requests without acknowledgment
7. **Deadline mentions**: "by Friday", "ASAP", "end of day", "tomorrow"
8. **Status update requests**: "where are we on...", "what's the status of..."
9. **Commitments to track**: "I'll send it today" = follow up if not done

## Important Rules
- A task does NOT need the word "task" or "urgent" to be a task
- "can you send over info about how you edit" IS a task
- "make sure to wrap up tyler vid first" IS a task (prioritization instruction)
- "I don't think I can finish this video in 4 days" IS a blocker needing PM action
- Automated check-in prompts from bots are NOT tasks themselves
- "New thumbnail needed" automated messages ARE tasks (Ram needs to create it)
- If uncertain whether something is a task, include it with confidence "low"

Return a JSON array. If no tasks found, return [].

Each task object:
{{
    "task_description": "Clear, actionable description of what needs to be done",
    "assigned_to": "Name of person who should do this (or 'Unknown')",
    "requested_by": "Name of person who made the request",
    "priority": "high" | "medium" | "low",
    "category": "editing" | "thumbnail" | "client_communication" | "scheduling" | "review" | "assets" | "blocker" | "follow_up" | "info_request" | "other",
    "source_message": "Exact Slack message (truncated to 150 chars)",
    "source_timestamp": "The Slack timestamp",
    "needs_response": true | false,
    "deadline_mentioned": "Any deadline mentioned, or null",
    "confidence": "high" | "medium" | "low",
    "video_reference": "ClientName Video #X if mentioned, or null"
}}

Respond with ONLY the JSON array, no other text."""


class SlackTaskScanner:
    """LLM-powered task extraction from Slack messages."""

    def __init__(self):
        # Slack client
        self.slack_token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN")
        if not self.slack_token:
            raise ValueError("SLACK_USER_TOKEN or SLACK_BOT_TOKEN required")
        self.slack_client = WebClient(token=self.slack_token)

        # Anthropic client
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY required")
        self.anthropic = Anthropic(api_key=self.anthropic_api_key)

        # Airtable setup
        self.airtable_api_key = os.getenv("AIRTABLE_API_KEY")
        self.airtable_base_id = os.getenv("AIRTABLE_BASE_ID")

        # Caches
        self._user_cache = {}
        self._team_members = None
        self._last_error = None
        self._errors = []

    # ==========================================================================
    # SLACK HELPERS (pattern from pm_analytics.py)
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
                "is_bot": user.get("is_bot", False)
            }
        except:
            self._user_cache[user_id] = {
                "id": user_id, "name": "Unknown", "is_bot": False
            }
        return self._user_cache[user_id]

    def _prefetch_all_users(self):
        """Fetch all users at once to avoid per-message API calls."""
        try:
            result = self.slack_client.users_list()
            for user in result.get("members", []):
                uid = user.get("id")
                if uid:
                    self._user_cache[uid] = {
                        "id": uid,
                        "name": user.get("real_name", user.get("name", "Unknown")),
                        "is_bot": user.get("is_bot", False)
                    }
        except SlackApiError:
            pass

    def _get_all_channels(self) -> List[Dict]:
        """Get all channels in workspace."""
        try:
            channels = []
            cursor = None
            while True:
                kwargs = {"types": "public_channel,private_channel", "limit": 200}
                if cursor:
                    kwargs["cursor"] = cursor
                result = self.slack_client.conversations_list(**kwargs)
                channels.extend(result.get("channels", []))
                cursor = result.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            return channels
        except SlackApiError:
            return []

    def _get_thread_replies(self, channel_id: str, thread_ts: str) -> List[Dict]:
        """Get replies to a thread, formatted consistently with channel messages."""
        try:
            result = self.slack_client.conversations_replies(
                channel=channel_id, ts=thread_ts
            )
            replies = []
            # Skip first message (it's the parent)
            for msg in result.get("messages", [])[1:]:
                user_info = self._get_slack_user(msg.get("user", "unknown"))
                ts = float(msg.get("ts", 0))
                dt = datetime.fromtimestamp(ts)
                replies.append({
                    "text": msg.get("text", ""),
                    "user_name": user_info["name"],
                    "is_bot": user_info["is_bot"],
                    "timestamp": msg.get("ts"),
                    "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                })
            return replies
        except SlackApiError:
            return []

    def _get_channel_messages(self, channel_id: str, oldest: float,
                               limit: int = 100, max_threads: int = 50) -> List[Dict]:
        """Get messages from a channel since a timestamp, including thread replies."""
        try:
            result = self.slack_client.conversations_history(
                channel=channel_id, oldest=str(oldest), limit=limit
            )
            messages = []
            threads_fetched = 0
            for msg in result.get("messages", []):
                user_info = self._get_slack_user(msg.get("user", "unknown"))
                ts = float(msg.get("ts", 0))
                dt = datetime.fromtimestamp(ts)

                thread_replies = []
                reply_count = msg.get("reply_count", 0)
                if reply_count > 0 and threads_fetched < max_threads:
                    thread_replies = self._get_thread_replies(channel_id, msg["ts"])
                    threads_fetched += 1

                messages.append({
                    "text": msg.get("text", ""),
                    "user_name": user_info["name"],
                    "is_bot": user_info["is_bot"],
                    "timestamp": msg.get("ts"),
                    "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                    "reply_count": reply_count,
                    "thread_replies": thread_replies,
                    "reactions": msg.get("reactions", []),
                    "subtype": msg.get("subtype"),
                })
            # Return in chronological order (oldest first)
            messages.reverse()
            return messages
        except SlackApiError:
            return []

    def _classify_channel(self, channel_name: str) -> str:
        """Classify channel type based on name."""
        if EDITOR_CHANNEL_PATTERN.search(channel_name):
            return "editor"
        if CLIENT_CHANNEL_PATTERN.search(channel_name):
            return "client"
        if THUMBNAIL_CHANNEL_PATTERN.search(channel_name):
            return "thumbnail"
        if PM_CHANNEL_PATTERN.search(channel_name):
            return "project_management"
        return "other"

    # ==========================================================================
    # AIRTABLE HELPERS
    # ==========================================================================

    def _get_team_members(self) -> List[Dict]:
        """Fetch team members from Airtable for context."""
        if self._team_members is not None:
            return self._team_members

        if not self.airtable_api_key or not self.airtable_base_id:
            self._team_members = []
            return self._team_members

        try:
            api = Api(self.airtable_api_key)
            table = api.table(self.airtable_base_id, "Team")
            records = table.all(fields=["Name", "Role", "Slack ID"])
            self._team_members = [
                {
                    "name": r["fields"].get("Name", "Unknown"),
                    "role": r["fields"].get("Role", "Unknown"),
                }
                for r in records
            ]
        except Exception:
            self._team_members = []

        return self._team_members

    def _get_active_videos(self) -> List[Dict]:
        """Fetch active (non-DONE) videos from Airtable."""
        if not self.airtable_api_key or not self.airtable_base_id:
            return []

        try:
            api = Api(self.airtable_api_key)
            table = api.table(self.airtable_base_id, "Videos")
            records = table.all(
                fields=[
                    "Video ID", "Client", "Video Number", "Editing Status",
                    "Assigned Editor", "Editor's Name", "Deadline"
                ],
                formula="NOT({Editing Status}='100 - Scheduled - DONE')"
            )

            videos = []
            for r in records:
                f = r["fields"]
                client_names = f.get("Client", [])
                editor_names = f.get("Editor's Name", [])
                videos.append({
                    "record_id": r["id"],
                    "video_id": f.get("Video ID"),
                    "client": client_names[0] if isinstance(client_names, list) and client_names else str(client_names),
                    "video_number": f.get("Video Number"),
                    "status": f.get("Editing Status", "Unknown"),
                    "editor": editor_names[0] if isinstance(editor_names, list) and editor_names else str(editor_names),
                    "deadline": f.get("Deadline"),
                })
            return videos
        except Exception:
            return []

    # ==========================================================================
    # PRE-FILTERING (deterministic, free)
    # ==========================================================================

    def _is_noise(self, msg: Dict) -> bool:
        """Determine if a message is noise (not worth sending to LLM)."""
        # Never filter out messages that have thread replies - the thread content matters
        if msg.get("reply_count", 0) > 0 or msg.get("thread_replies"):
            return False

        text = msg.get("text", "").strip()

        # System messages (joins, leaves, topic changes)
        if msg.get("subtype") in [
            "channel_join", "channel_leave", "channel_topic",
            "channel_purpose", "channel_name", "pinned_item"
        ]:
            return True

        # Empty or very short
        if len(text) < 8:
            return True

        # Pure emoji
        if re.match(r'^(\:[\w\+\-]+\:\s*)+$', text):
            return True

        # Pure acknowledgments
        text_lower = text.lower().strip()
        if len(text_lower) < 15:
            for pattern in ACKNOWLEDGMENT_PATTERNS:
                if re.match(pattern, text_lower, re.IGNORECASE):
                    return True

        return False

    def _prefilter_messages(self, messages: List[Dict]) -> List[Dict]:
        """Remove noise messages before LLM analysis."""
        return [m for m in messages if not self._is_noise(m)]

    # ==========================================================================
    # LLM ANALYSIS
    # ==========================================================================

    def _build_prompt(self, channel_name: str, channel_type: str,
                      messages: List[Dict]) -> str:
        """Build the task extraction prompt for a channel."""
        # Team members block
        team = self._get_team_members()
        if team:
            team_block = "\n".join(
                f"- {m['name']} ({m['role']})" for m in team
            )
        else:
            team_block = "(Team member data unavailable)"

        # Messages block (with thread replies indented)
        msg_lines = []
        for m in messages:
            msg_lines.append(
                f"[{m['datetime']}] {m['user_name']}: {m['text'][:500]}"
            )
            for reply in m.get("thread_replies", []):
                msg_lines.append(
                    f"  -> [{reply['datetime']}] {reply['user_name']}: {reply['text'][:500]}"
                )
        messages_block = "\n".join(msg_lines)

        return TASK_EXTRACTION_PROMPT.format(
            channel_name=channel_name,
            channel_type=channel_type,
            team_members_block=team_block,
            messages_block=messages_block,
        )

    def _call_claude(self, prompt: str) -> List[Dict]:
        """Send prompt to Claude and parse JSON task array."""
        try:
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Handle markdown code blocks
            if response_text.startswith('```'):
                response_text = response_text.split('\n', 1)[1]
                response_text = response_text.rsplit('```', 1)[0]

            tasks = json.loads(response_text)
            if isinstance(tasks, list):
                return tasks
            return []
        except json.JSONDecodeError as e:
            self._last_error = f"JSON parse error: {str(e)}"
            return []
        except Exception as e:
            self._last_error = f"Claude API error: {str(e)}"
            return []

    # ==========================================================================
    # AIRTABLE CROSS-REFERENCE
    # ==========================================================================

    def _cross_reference(self, tasks: List[Dict],
                         active_videos: List[Dict]) -> List[Dict]:
        """Match extracted tasks against Airtable to mark tracked/untracked."""
        # Build lookup structures
        editor_videos = {}
        client_videos = {}
        for v in active_videos:
            editor = (v.get("editor") or "").lower()
            client = (v.get("client") or "").lower()
            if editor:
                editor_videos.setdefault(editor, []).append(v)
            if client:
                client_videos.setdefault(client, []).append(v)

        for task in tasks:
            task["is_tracked"] = False
            task["airtable_match"] = None

            video_ref = task.get("video_reference")
            if video_ref:
                # Try to match "ClientName Video #X"
                match = re.match(r'(.+?)\s*(?:Video|Shorts)\s*#?(\d+)', video_ref, re.IGNORECASE)
                if match:
                    client_name = match.group(1).strip().lower()
                    video_num = match.group(2)
                    for v in client_videos.get(client_name, []):
                        if str(v.get("video_number")) == video_num:
                            task["is_tracked"] = True
                            task["airtable_match"] = {
                                "record_id": v["record_id"],
                                "status": v["status"],
                                "deadline": v["deadline"],
                                "editor": v["editor"],
                            }
                            break

            # If no match by video ref, check if task is about editing/review
            # for a video that's in the pipeline (loose match by assignee)
            if not task["is_tracked"] and task.get("category") in [
                "editing", "review", "scheduling"
            ]:
                assignee = (task.get("assigned_to") or "").lower()
                if assignee in editor_videos:
                    # Task is about editing work for someone who has active videos
                    # This is likely tracked in Airtable already
                    task["is_tracked"] = True
                    vids = editor_videos[assignee]
                    task["airtable_match"] = {
                        "record_id": vids[0]["record_id"],
                        "status": vids[0]["status"],
                        "note": f"{len(vids)} active video(s) for {assignee}"
                    }

        return tasks

    # ==========================================================================
    # MAIN ACTIONS
    # ==========================================================================

    def extract_tasks(self, hours: int = 24, channels: Optional[List[str]] = None,
                      dry_run: bool = False) -> Dict:
        """Full scan: collect messages, LLM analysis, Airtable cross-reference."""
        start_time = datetime.now()
        oldest = (datetime.now() - timedelta(hours=hours)).timestamp()

        # Prefetch all users to avoid per-message API calls
        self._prefetch_all_users()

        # Get channels
        all_channels = self._get_all_channels()

        # Filter to requested channels if specified
        if channels:
            channel_names_lower = [c.lower().strip('#') for c in channels]
            all_channels = [
                ch for ch in all_channels
                if ch["name"].lower() in channel_names_lower
            ]

        # Collect and prefilter messages per channel
        channel_data = []
        total_raw = 0
        total_filtered = 0

        for ch in all_channels:
            ch_name = ch["name"]
            ch_id = ch["id"]
            ch_type = self._classify_channel(ch_name)

            raw_messages = self._get_channel_messages(ch_id, oldest)
            total_raw += len(raw_messages)

            filtered = self._prefilter_messages(raw_messages)
            total_filtered += len(filtered)

            if filtered:
                thread_reply_count = sum(
                    len(m.get("thread_replies", [])) for m in filtered
                )
                channel_data.append({
                    "name": ch_name,
                    "id": ch_id,
                    "type": ch_type,
                    "messages": filtered,
                    "raw_count": len(raw_messages),
                    "filtered_count": len(filtered),
                    "thread_reply_count": thread_reply_count,
                })

        # Dry run - return counts only, no LLM cost
        if dry_run:
            return {
                "dry_run": True,
                "scan_metadata": {
                    "scan_time": datetime.now().isoformat(),
                    "hours_scanned": hours,
                    "channels_scanned": len(channel_data),
                    "total_messages_raw": total_raw,
                    "total_messages_after_filter": total_filtered,
                    "messages_filtered_out": total_raw - total_filtered,
                    "estimated_llm_calls": len(channel_data),
                    "estimated_cost_usd": round(len(channel_data) * 0.008, 3),
                },
                "total_thread_replies": sum(cd["thread_reply_count"] for cd in channel_data),
                "channels": [
                    {
                        "name": cd["name"],
                        "type": cd["type"],
                        "raw_messages": cd["raw_count"],
                        "after_filter": cd["filtered_count"],
                        "thread_replies": cd["thread_reply_count"],
                    }
                    for cd in channel_data
                ]
            }

        # Phase 2: LLM analysis per channel
        all_tasks = []
        llm_calls = 0

        for cd in channel_data:
            # Skip channels with very few messages
            if cd["filtered_count"] < 2:
                continue

            prompt = self._build_prompt(cd["name"], cd["type"], cd["messages"])
            tasks = self._call_claude(prompt)
            llm_calls += 1

            if self._last_error:
                self._errors.append(f"{cd['name']}: {self._last_error}")
                self._last_error = None

            # Attach channel info to each task
            for task in tasks:
                task["source_channel"] = cd["name"]
                task["source_channel_id"] = cd["id"]

            all_tasks.extend(tasks)

        # Phase 3: Airtable cross-reference
        active_videos = self._get_active_videos()
        all_tasks = self._cross_reference(all_tasks, active_videos)

        # Deduplicate similar tasks across channels
        all_tasks = self._deduplicate(all_tasks)

        # Build summary
        summary = self._build_summary(all_tasks)

        elapsed = (datetime.now() - start_time).total_seconds()

        result = {
            "scan_metadata": {
                "scan_time": datetime.now().isoformat(),
                "hours_scanned": hours,
                "channels_scanned": len(channel_data),
                "messages_analyzed": total_filtered,
                "messages_filtered_out": total_raw - total_filtered,
                "llm_calls_made": llm_calls,
                "estimated_cost_usd": round(llm_calls * 0.008, 3),
                "model_used": "claude-sonnet-4-20250514",
                "elapsed_seconds": round(elapsed, 1),
            },
            "tasks": all_tasks,
            "summary": summary,
        }

        if self._errors:
            result["errors"] = self._errors

        return result

    def scan_channel(self, channel: str, hours: int = 48) -> Dict:
        """Scan a single channel."""
        return self.extract_tasks(hours=hours, channels=[channel])

    def get_untracked(self, hours: int = 24) -> Dict:
        """Get only tasks NOT tracked in Airtable."""
        result = self.extract_tasks(hours=hours)

        # Filter to untracked only
        untracked = [t for t in result["tasks"] if not t.get("is_tracked")]

        result["tasks"] = untracked
        result["summary"] = self._build_summary(untracked)
        result["summary"]["note"] = "Filtered to untracked tasks only"

        return result

    # ==========================================================================
    # HELPERS
    # ==========================================================================

    def _deduplicate(self, tasks: List[Dict]) -> List[Dict]:
        """Remove duplicate tasks that appear across channels."""
        if not tasks:
            return tasks

        seen = []
        unique = []

        for task in tasks:
            desc = task.get("task_description", "").lower().strip()
            assignee = (task.get("assigned_to") or "").lower()
            key = f"{assignee}:{desc[:60]}"

            is_dup = False
            for seen_key in seen:
                # Simple similarity: same first 60 chars of description + same assignee
                if key == seen_key:
                    is_dup = True
                    break

            if not is_dup:
                seen.append(key)
                unique.append(task)

        return unique

    def _build_summary(self, tasks: List[Dict]) -> Dict:
        """Build aggregate summary from tasks."""
        by_priority = {"high": 0, "medium": 0, "low": 0}
        by_category = {}
        by_assignee = {}
        blockers = 0
        tracked = 0
        untracked = 0

        for t in tasks:
            pri = t.get("priority", "low")
            by_priority[pri] = by_priority.get(pri, 0) + 1

            cat = t.get("category", "other")
            by_category[cat] = by_category.get(cat, 0) + 1

            assignee = t.get("assigned_to", "Unknown")
            by_assignee[assignee] = by_assignee.get(assignee, 0) + 1

            if t.get("category") == "blocker":
                blockers += 1

            if t.get("is_tracked"):
                tracked += 1
            else:
                untracked += 1

        return {
            "total_tasks": len(tasks),
            "by_priority": by_priority,
            "by_category": by_category,
            "by_assignee": by_assignee,
            "tracked_in_airtable": tracked,
            "untracked_new": untracked,
            "blockers": blockers,
        }


# ==========================================================================
# CLI ENTRY POINT
# ==========================================================================

def main():
    """CLI interface for Slack Task Scanner."""
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action parameter",
            "available_actions": ["extract_tasks", "scan_channel", "get_untracked"]
        }))
        sys.exit(1)

    action = sys.argv[1]

    # Parse optional JSON params
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            params = {}

    try:
        scanner = SlackTaskScanner()

        if action == "extract_tasks":
            hours = params.get("hours", 24)
            channels = params.get("channels")
            dry_run = params.get("dry_run", False)
            result = scanner.extract_tasks(hours, channels, dry_run)

        elif action == "scan_channel":
            channel = params.get("channel")
            if not channel:
                print(json.dumps({"error": "channel parameter required for scan_channel"}))
                sys.exit(1)
            hours = params.get("hours", 48)
            result = scanner.scan_channel(channel, hours)

        elif action == "get_untracked":
            hours = params.get("hours", 24)
            result = scanner.get_untracked(hours)

        else:
            print(json.dumps({
                "error": f"Unknown action: {action}",
                "available_actions": ["extract_tasks", "scan_channel", "get_untracked"]
            }))
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
