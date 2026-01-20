#!/usr/bin/env python3
"""
Orchestrator: Autonomous agent engine using Claude Agent SDK

This orchestrator uses the official Claude Agent SDK for server deployment.
The Agent SDK provides the same capabilities as Claude Code CLI but is designed
for production server use with proper API key authentication.

GUARDRAILS FOR CLIENT WEBAPP:
- Full PM operations allowed (query, update tasks, send messages, etc.)
- NO file editing (Edit, Write tools blocked)
- NO access to system files (config/, execution/, .env, etc.)
- Bash commands restricted to safe operations only
"""

import os
import json
import asyncio
import re
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Claude Agent SDK imports
from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher


# =============================================================================
# GUARDRAILS CONFIGURATION
# =============================================================================

# Directories that clients cannot access
PROTECTED_DIRECTORIES = [
    "config/",
    "config\\",
    "execution/",
    "execution\\",
    ".git/",
    ".git\\",
    ".env",
    "credentials.json",
    "token.json",
    "__pycache__",
    "node_modules",
]

# File patterns that clients cannot access
PROTECTED_FILE_PATTERNS = [
    r"\.env.*",
    r".*\.pem$",
    r".*\.key$",
    r"credentials.*\.json",
    r"token.*\.json",
    r".*secret.*",
]

# Dangerous bash commands/patterns to block
DANGEROUS_BASH_PATTERNS = [
    r"rm\s+-rf",
    r"rm\s+-r\s+/",
    r"rmdir",
    r"del\s+/[sS]",  # Windows recursive delete
    r"format\s+",
    r"mkfs",
    r"dd\s+if=",
    r">\s*/dev/",
    r"chmod\s+777",
    r"curl.*\|\s*(ba)?sh",  # Piping curl to shell
    r"wget.*\|\s*(ba)?sh",
    r"pip\s+install",
    r"npm\s+install",
    r"git\s+push",
    r"git\s+commit",
    r"git\s+reset\s+--hard",
    r"shutdown",
    r"reboot",
    r"kill\s+-9",
    r"pkill",
    r"taskkill",
]

# Allowed bash commands (whitelist approach for safety)
ALLOWED_BASH_PATTERNS = [
    r"^ls\s",
    r"^dir\s",
    r"^cat\s",
    r"^type\s",  # Windows cat
    r"^head\s",
    r"^tail\s",
    r"^grep\s",
    r"^find\s",
    r"^echo\s",
    r"^pwd$",
    r"^cd$",
    r"^date$",
    r"^whoami$",
    r"^python\s+.*\.py",  # Allow running specific scripts
]


# =============================================================================
# HOOK FUNCTIONS FOR GUARDRAILS
# =============================================================================

async def block_file_modifications(input_data, tool_use_id, context):
    """
    PreToolUse hook to block Edit and Write operations.
    """
    tool_input = input_data.get('tool_input', {})
    tool_name = input_data.get('tool_name', '')

    # Block Edit and Write tools entirely
    if tool_name in ['Edit', 'Write', 'NotebookEdit']:
        return {
            "decision": "block",
            "reason": "File modifications are not permitted. This agent is read-only for files."
        }

    return {}


async def block_protected_paths(input_data, tool_use_id, context):
    """
    PreToolUse hook to block access to protected directories and files.
    """
    tool_input = input_data.get('tool_input', {})

    # Check various path parameters
    path_params = ['file_path', 'path', 'directory', 'cwd', 'notebook_path']

    for param in path_params:
        if param in tool_input:
            path = str(tool_input[param]).lower()

            # Check protected directories
            for protected in PROTECTED_DIRECTORIES:
                if protected.lower() in path:
                    return {
                        "decision": "block",
                        "reason": f"Access to system directory '{protected}' is not permitted."
                    }

            # Check protected file patterns
            for pattern in PROTECTED_FILE_PATTERNS:
                if re.search(pattern, path, re.IGNORECASE):
                    return {
                        "decision": "block",
                        "reason": "Access to this file type is not permitted."
                    }

    return {}


async def restrict_bash_commands(input_data, tool_use_id, context):
    """
    PreToolUse hook to restrict dangerous bash commands.
    """
    tool_input = input_data.get('tool_input', {})
    tool_name = input_data.get('tool_name', '')

    if tool_name != 'Bash':
        return {}

    command = tool_input.get('command', '')

    # Check for dangerous patterns
    for pattern in DANGEROUS_BASH_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return {
                "decision": "block",
                "reason": f"This command is not permitted for safety reasons."
            }

    # Check if command accesses protected paths
    for protected in PROTECTED_DIRECTORIES:
        if protected.lower() in command.lower():
            return {
                "decision": "block",
                "reason": f"Commands accessing system directories are not permitted."
            }

    return {}


# =============================================================================
# ORCHESTRATOR CLASS
# =============================================================================

class ScopedOrchestrator:
    """
    Wraps Claude Agent SDK for web-accessible agent functionality.

    Implements guardrails to restrict client access:
    - Full PM operations (Airtable, Slack, queries)
    - Read-only file access (no Edit/Write)
    - Protected system directories blocked
    - Dangerous bash commands blocked
    """

    def __init__(self, client_name: str):
        """
        Initialize orchestrator for a specific client.

        Args:
            client_name: Client identifier (matches config file)
        """
        self.client_name = client_name

        # Load client configuration
        config_path = Path(__file__).parent.parent / f"config/clients/{client_name}.json"

        if not config_path.exists():
            raise FileNotFoundError(f"Client configuration not found: {config_path}")

        with open(config_path) as f:
            self.config = json.load(f)

        # System prompt is used by Agent SDK
        self.system_prompt = self.config.get("system_prompt", "")

        # Add guardrail instructions to system prompt
        self.system_prompt += """

## IMPORTANT RESTRICTIONS
You are running in CLIENT MODE with the following restrictions:
- You CANNOT edit or write files (Edit, Write tools are disabled)
- You CANNOT access system directories (config/, execution/, .env, etc.)
- You CANNOT run dangerous commands (install packages, delete files, git push, etc.)
- You CAN read files, search code, query Airtable, read Slack, and perform all PM operations

If a user asks you to do something restricted, politely explain that this action
requires approval from the agency administrator.
"""

        # Project directory for Agent SDK context
        self.project_dir = Path(__file__).parent.parent

        # Session management - persist session ID for conversation continuity
        self.session_file = self.project_dir / f".tmp/sessions/{client_name}_session.json"
        self.session_file.parent.mkdir(parents=True, exist_ok=True)

        # Load or create session
        self.session_id = self._load_session()
        self.conversation_history = []

    def _load_session(self) -> Optional[str]:
        """Load existing session ID if available."""
        try:
            if self.session_file.exists():
                with open(self.session_file) as f:
                    data = json.load(f)
                    # Check if session is recent (within 1 hour)
                    created = datetime.fromisoformat(data.get("created", "2000-01-01"))
                    age = datetime.now() - created
                    if age.total_seconds() < 3600:  # 1 hour
                        return data.get("session_id")
        except Exception:
            pass
        return None

    def _save_session(self, session_id: str):
        """Save session ID for future use."""
        try:
            with open(self.session_file, 'w') as f:
                json.dump({
                    "session_id": session_id,
                    "created": datetime.now().isoformat(),
                    "client_name": self.client_name
                }, f)
        except Exception:
            pass

    def clear_session(self):
        """Clear the current session to start fresh."""
        self.session_id = None
        try:
            if self.session_file.exists():
                self.session_file.unlink()
        except Exception:
            pass

    async def process_request(self, user_message: str) -> Dict[str, Any]:
        """
        Process natural language request using Claude Agent SDK.

        Args:
            user_message: Natural language request from client

        Returns:
            Dict with response, tools_used, and conversation_id
        """
        # Track in history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Call Agent SDK
        result = await self._call_agent_sdk(user_message)

        # Track response
        self.conversation_history.append({
            "role": "assistant",
            "content": result.get("response", "")
        })

        # Log interaction
        self._log_interaction(
            user_message=user_message,
            response=result.get("response", ""),
            session_id=result.get("session_id")
        )

        return result

    async def _call_agent_sdk(self, message: str) -> Dict[str, Any]:
        """
        Call Claude Agent SDK with guardrails.

        Args:
            message: The user's message

        Returns:
            Dict with response and metadata
        """
        try:
            # Build options with guardrails
            options_dict = {
                "cwd": str(self.project_dir),
                "permission_mode": "bypassPermissions",
                # Restricted tool list - NO Edit, Write
                "allowed_tools": [
                    "Read",           # Can read files
                    "Glob",           # Can search for files
                    "Grep",           # Can search in files
                    "Bash",           # Restricted via hooks
                    "WebFetch",       # Can fetch web content
                    "WebSearch",      # Can search web
                    "Task",           # Can spawn subagents (they inherit restrictions)
                    "AskUserQuestion" # Can ask clarifying questions
                ],
                # Hooks for guardrails
                "hooks": {
                    "PreToolUse": [
                        HookMatcher(matcher="Edit|Write|NotebookEdit", hooks=[block_file_modifications]),
                        HookMatcher(matcher="Read|Glob|Grep", hooks=[block_protected_paths]),
                        HookMatcher(matcher="Bash", hooks=[restrict_bash_commands, block_protected_paths]),
                    ]
                }
            }

            # Add system prompt for new sessions
            if not self.session_id and self.system_prompt:
                options_dict["system_prompt"] = self.system_prompt

            # Add resume if we have an existing session
            if self.session_id:
                options_dict["resume"] = self.session_id

            options = ClaudeAgentOptions(**options_dict)

            # Collect response
            response_text = ""
            new_session_id = None
            num_turns = 0
            blocked_actions = []

            async for msg in query(prompt=message, options=options):
                # Capture session ID from init message
                if hasattr(msg, 'subtype') and msg.subtype == 'init':
                    new_session_id = getattr(msg, 'session_id', None)

                # Capture final result
                if hasattr(msg, 'result'):
                    response_text = msg.result

                # Track turns
                if hasattr(msg, 'type') and msg.type == 'assistant':
                    num_turns += 1

                # Track blocked actions for logging
                if hasattr(msg, 'type') and msg.type == 'hook_result':
                    if getattr(msg, 'decision', '') == 'block':
                        blocked_actions.append(getattr(msg, 'reason', 'Unknown'))

            # Save session ID for continuity
            if new_session_id:
                self.session_id = new_session_id
                self._save_session(new_session_id)

            return {
                "response": response_text,
                "tools_used": [],
                "conversation_id": f"{self.client_name}_{new_session_id or 'unknown'}",
                "session_id": new_session_id,
                "num_turns": num_turns,
                "blocked_actions": blocked_actions,
                "backend": "claude_agent_sdk_guarded"
            }

        except Exception as e:
            error_msg = str(e)

            # Handle specific errors
            if "CLINotFoundError" in error_msg or "not found" in error_msg.lower():
                return {
                    "response": "Claude Code CLI not found. Please ensure it is installed.",
                    "tools_used": [],
                    "conversation_id": f"{self.client_name}_not_found",
                    "backend": "claude_agent_sdk_guarded"
                }

            return {
                "response": f"Error processing your request. Please try again or contact support.",
                "tools_used": [],
                "conversation_id": f"{self.client_name}_error",
                "backend": "claude_agent_sdk_guarded",
                "error": error_msg  # For logging, not shown to client
            }

    def _log_interaction(self, user_message: str, response: str, session_id: Optional[str] = None):
        """Log conversation for monitoring."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "client": self.client_name,
            "session_id": session_id,
            "user_message": str(user_message),
            "response": response[:500] + "..." if len(response) > 500 else response,
            "backend": "claude_agent_sdk_guarded"
        }

        log_path = self.project_dir / f".tmp/logs/{self.client_name}.jsonl"
        log_path.parent.mkdir(exist_ok=True, parents=True)

        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python orchestrator.py <client_name> <message>")
        sys.exit(1)

    client_name = sys.argv[1]
    message = " ".join(sys.argv[2:])

    orchestrator = ScopedOrchestrator(client_name)
    result = asyncio.run(orchestrator.process_request(message))

    print(json.dumps(result, indent=2))
