#!/usr/bin/env python3
"""
Summary Generator - LLM-powered summary from aggregated PM data

Takes output from multiple data-gathering steps (task scanner, channel reads,
PM analytics) and produces a concise, Slack-formatted summary.

Actions:
    generate  - Create a summary from input_data dict

Usage:
    python summary_generator.py generate '{"input_data": {...}, "recipient_name": "Simon", "time_of_day": "morning"}'
"""

import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from anthropic import Anthropic


SYSTEM_PROMPT = """You are a project management assistant generating Slack DM summaries for a YouTube video production agency (KS Media).

Your #1 job: surface things that need action. Every message you write should make it obvious what the recipient needs to do RIGHT NOW.

Rules:
- Format for Slack DM: use *bold* for emphasis, bullet points, and minimal emoji
- ALWAYS use "ClientName Video #X" format (e.g., "Taylor Video #11"). NEVER show raw Video IDs or Airtable record IDs
- Include editor names and video status when relevant
- Keep the total message under 2000 characters for Slack readability
- ALWAYS end with a numbered *Action Items* list — concrete tasks with specific details (names, counts, deadlines)
- Be direct and concise — this is an operational update, not a report

What to extract and highlight:
- *Direct questions or requests* aimed at the recipient — these are TOP PRIORITY. If someone asks "did you send out 2 George vids?" that means "2 George videos need to be sent out" is an action item
- *Pending deliverables* — videos that need sending, reviews, approvals, uploads
- *Blockers* — anything stalled, waiting, or stuck
- *Unanswered messages* — people waiting for a reply
- *Status changes* — videos that moved stages, editors who finished work

When someone asks "did you do X?" or "have you sent X?" — treat that as "X still needs to be done" unless there's a clear reply confirming it was done."""


def build_prompt(input_data: dict, recipient_name: str, time_of_day: str) -> str:
    """Build the user prompt from aggregated step data."""
    time_labels = {
        "morning": "Morning Update (9:30 AM)",
        "midday": "Midday Update (12:15 PM)",
        "afternoon": "Afternoon Wrap-up (3:00 PM)",
    }
    label = time_labels.get(time_of_day, "Status Update")

    sections = []

    # Task scanner results
    scan_data = input_data.get("scan_tasks", {})
    if scan_data:
        sections.append(f"### Tasks Found in Slack (LLM scan)\n```json\n{json.dumps(scan_data, indent=2)[:3000]}\n```")

    # Channel messages
    channel_data = input_data.get("read_pm_channel", {})
    if channel_data:
        # Truncate to keep prompt manageable
        if isinstance(channel_data, list):
            channel_data = channel_data[:20]
        sections.append(f"### #project-manager Messages\n```json\n{json.dumps(channel_data, indent=2)[:3000]}\n```")

    # Attention needed
    attention_data = input_data.get("attention_needed", {})
    if attention_data:
        sections.append(f"### Items Needing Attention\n```json\n{json.dumps(attention_data, indent=2)[:2000]}\n```")

    # Unfollowed messages
    unfollowed_data = input_data.get("unfollowed_messages", {})
    if unfollowed_data:
        sections.append(f"### Unanswered Messages\n```json\n{json.dumps(unfollowed_data, indent=2)[:2000]}\n```")

    data_block = "\n\n".join(sections) if sections else "No data gathered for this period."

    tone_guide = {
        "morning": "Give a comprehensive overview of what needs attention today. Set the agenda.",
        "midday": "Focus on changes since the morning. What's progressed? What's stalled? Any new blockers?",
        "afternoon": "Wrap up the day. What was accomplished? What's still open? What carries over to tomorrow?",
    }
    tone = tone_guide.get(time_of_day, "Provide a balanced status update.")

    return f"""Generate a *{label}* Slack DM for {recipient_name}.

{tone}

## Data Sources

{data_block}

## Critical Instructions
1. Scan ALL messages for direct questions, requests, or asks aimed at {recipient_name} — these become the top action items
2. When someone asks "did you do X?" or "can you send X?" — that means X is PENDING and needs doing. Surface it as: "*X needs to be done*"
3. Include specific details: video counts, client names, editor names, deadlines
4. Do NOT just list raw messages. Synthesize them into actionable intel.

## Output
Write the Slack message now. Start with a one-line greeting, then the update grouped by priority. End with numbered action items. Keep it under 2000 characters."""


def generate(input_data: dict, recipient_name: str = "PM", time_of_day: str = "update") -> dict:
    """Generate a summary using Claude."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"success": False, "error": "ANTHROPIC_API_KEY not set"}

    model = os.getenv("SUMMARY_MODEL", "claude-sonnet-4-20250514")
    client = Anthropic(api_key=api_key)

    prompt = build_prompt(input_data, recipient_name, time_of_day)

    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    summary = response.content[0].text.strip()
    tokens = response.usage.input_tokens + response.usage.output_tokens

    return {
        "success": True,
        "summary": summary,
        "tokens_used": tokens,
        "model": model,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action. Usage: summary_generator.py generate '<json_params>'"
        }))
        sys.exit(1)

    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON params"}))
            sys.exit(1)

    if action == "generate":
        result = generate(
            input_data=params.get("input_data", {}),
            recipient_name=params.get("recipient_name", "PM"),
            time_of_day=params.get("time_of_day", "update"),
        )
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"error": f"Unknown action: {action}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
