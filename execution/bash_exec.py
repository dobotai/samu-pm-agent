#!/usr/bin/env python3
"""
Bash/command execution tool.
Runs shell commands and returns output.
"""

import sys
import json
import subprocess
import os
from pathlib import Path


def execute_command(command: str, timeout: int = 120, cwd: str = None) -> dict:
    """Execute a shell command and return the result."""
    try:
        # Use the working directory if provided
        working_dir = cwd if cwd else os.getcwd()

        # Determine shell based on OS
        if os.name == 'nt':  # Windows
            shell = True
            executable = None
        else:  # Unix/Linux/Mac
            shell = True
            executable = '/bin/bash'

        result = subprocess.run(
            command,
            shell=shell,
            executable=executable,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        output = {
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout[:30000] if result.stdout else "",  # Limit output size
            "stderr": result.stderr[:10000] if result.stderr else "",
            "success": result.returncode == 0,
            "working_directory": working_dir
        }

        # Truncation notice
        if result.stdout and len(result.stdout) > 30000:
            output["stdout_truncated"] = True
        if result.stderr and len(result.stderr) > 10000:
            output["stderr_truncated"] = True

        return output

    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "error": f"Command timed out after {timeout} seconds",
            "success": False
        }
    except Exception as e:
        return {
            "command": command,
            "error": str(e),
            "success": False
        }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing command parameter",
            "usage": "bash_exec.py <command_json>",
            "example": 'bash_exec.py \'{"command": "ls -la"}\''
        }))
        sys.exit(1)

    # Parse JSON params
    try:
        params = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        # Treat the whole argument as the command
        params = {"command": " ".join(sys.argv[1:])}

    command = params.get("command")
    if not command:
        print(json.dumps({"error": "command is required"}))
        sys.exit(1)

    timeout = int(params.get("timeout", 120))
    cwd = params.get("cwd") or params.get("working_directory")

    result = execute_command(command, timeout=timeout, cwd=cwd)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
