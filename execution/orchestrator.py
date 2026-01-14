#!/usr/bin/env python3
"""
Orchestrator: Autonomous agent engine for client mode
Reads client config, processes natural language requests, executes tools
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any
from anthropic import Anthropic
from datetime import datetime


class ScopedOrchestrator:
    """
    Scoped autonomous orchestrator for client agents.

    Loads client configuration, processes natural language requests,
    calls Claude API to decide which tools to use, executes tools,
    and maintains conversation history.
    """

    def __init__(self, client_name: str):
        """
        Initialize orchestrator for a specific client.

        Args:
            client_name: Client identifier (matches config file)
        """
        self.client_name = client_name
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # Load client configuration
        config_path = Path(__file__).parent.parent / f"config/clients/{client_name}.json"

        if not config_path.exists():
            raise FileNotFoundError(f"Client configuration not found: {config_path}")

        with open(config_path) as f:
            self.config = json.load(f)

        self.system_prompt = self.config["system_prompt"]
        self.available_tools = self.config["available_tools"]
        self.constraints = self.config.get("constraints", [])
        self.conversation_history = []

    def process_request(self, user_message: str) -> Dict[str, Any]:
        """
        Process natural language request from client.

        Args:
            user_message: Natural language request from client

        Returns:
            Dict with response, tools_used, and conversation_id
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Build tool definitions for Claude API
        tools = self._build_tool_definitions()

        # Call Claude API with tools
        response = self.client.messages.create(
            model="claude-opus-4-20250514",  # Use Opus 4.5
            max_tokens=4096,
            system=self._build_system_prompt(),
            messages=self.conversation_history,
            tools=tools if tools else None
        )

        # Process response and handle tool calls
        result = self._process_response(response)

        return result

    def _build_system_prompt(self) -> str:
        """
        Build comprehensive system prompt with constraints.

        Returns:
            Complete system prompt string
        """
        prompt = f"{self.system_prompt}\n\n"

        if self.constraints:
            prompt += "CONSTRAINTS:\n"
            for constraint in self.constraints:
                prompt += f"- {constraint}\n"
            prompt += "\n"

        prompt += """When you need to recommend a new tool (functionality not available):
1. Clearly explain what's not available
2. Describe what tool would be needed
3. Suggest contacting the agency to add it
4. Log it as a feature request

Always be helpful, professional, and work within your defined boundaries."""

        return prompt

    def _build_tool_definitions(self) -> List[Dict]:
        """
        Convert config tools to Claude API tool format.

        Returns:
            List of tool definitions for Claude API
        """
        tool_defs = []

        for tool in self.available_tools:
            tool_def = {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": {
                    "type": "object",
                    "properties": tool.get("input_schema", {}).get("properties", {}),
                    "required": tool.get("input_schema", {}).get("required", [])
                }
            }
            tool_defs.append(tool_def)

        return tool_defs

    def _process_response(self, response) -> Dict[str, Any]:
        """
        Process Claude's response and execute any tool calls.
        Handles multi-turn tool use by looping until no more tools are called.

        Args:
            response: Response from Claude API

        Returns:
            Dict with final response and metadata
        """
        all_tool_results = []
        final_text = ""
        current_response = response
        max_iterations = 10  # Safety limit to prevent infinite loops

        for iteration in range(max_iterations):
            assistant_message = {
                "role": "assistant",
                "content": []
            }
            tool_results = []

            # Process content blocks
            for block in current_response.content:
                if block.type == "text":
                    final_text = block.text
                    assistant_message["content"].append(block)

                elif block.type == "tool_use":
                    # Execute the tool
                    tool_result = self._execute_tool(
                        tool_name=block.name,
                        tool_input=block.input,
                        tool_use_id=block.id
                    )
                    tool_results.append(tool_result)
                    all_tool_results.append(tool_result)
                    assistant_message["content"].append(block)

            # Add assistant message to history
            self.conversation_history.append(assistant_message)

            # If no tools were used, we're done
            if not tool_results:
                break

            # Add tool results to conversation
            self.conversation_history.append({
                "role": "user",
                "content": tool_results
            })

            # Get next response after tool execution
            current_response = self.client.messages.create(
                model="claude-opus-4-20250514",
                max_tokens=4096,
                system=self._build_system_prompt(),
                messages=self.conversation_history,
                tools=self._build_tool_definitions() if self.available_tools else None
            )

        # Log conversation
        self._log_interaction(
            user_message="[see conversation history]",
            response=final_text,
            tools_used=[r.get("tool_use_id", "unknown") for r in all_tool_results]
        )

        return {
            "response": final_text,
            "tools_used": all_tool_results,
            "conversation_id": f"{self.client_name}_{datetime.now().isoformat()}"
        }

    def _execute_tool(self, tool_name: str, tool_input: Dict, tool_use_id: str) -> Dict:
        """
        Execute a tool by running its script.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            tool_use_id: Unique ID for this tool use

        Returns:
            Tool result dict for Claude API
        """
        # Find tool config
        tool_config = next((t for t in self.available_tools if t["name"] == tool_name), None)

        if not tool_config:
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps({"error": f"Tool {tool_name} not found"})
            }

        script_path = tool_config["script"]

        # Merge fixed parameters from config with dynamic input
        params = tool_config.get("parameters", {}).copy()
        params.update(tool_input)

        # Build command
        cmd = ["python", script_path]
        for key, value in params.items():
            cmd.extend([f"--{key}", str(value)])

        try:
            # Execute script
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=Path(__file__).parent.parent
            )

            if result.returncode == 0:
                # Success
                output = result.stdout
                try:
                    output_data = json.loads(output)
                except:
                    output_data = {"output": output}

                return {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(output_data)
                }
            else:
                # Error
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps({
                        "error": result.stderr,
                        "stdout": result.stdout
                    }),
                    "is_error": True
                }

        except subprocess.TimeoutExpired:
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps({"error": "Tool execution timeout (60s)"}),
                "is_error": True
            }
        except Exception as e:
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps({"error": str(e)}),
                "is_error": True
            }

    def _log_interaction(self, user_message: str, response: str, tools_used: List[str]):
        """
        Log conversation for monitoring.

        Args:
            user_message: User's message
            response: Agent's response
            tools_used: List of tools that were used
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "client": self.client_name,
            "user_message": str(user_message),
            "response": response,
            "tools_used": tools_used
        }

        # Append to log file
        log_path = Path(__file__).parent.parent / f".tmp/logs/{self.client_name}.jsonl"
        log_path.parent.mkdir(exist_ok=True, parents=True)

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


if __name__ == "__main__":
    # Simple test
    import sys

    if len(sys.argv) < 3:
        print("Usage: python orchestrator.py <client_name> <message>")
        sys.exit(1)

    client_name = sys.argv[1]
    message = " ".join(sys.argv[2:])

    orchestrator = ScopedOrchestrator(client_name)
    result = orchestrator.process_request(message)

    print(json.dumps(result, indent=2))
