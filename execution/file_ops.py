#!/usr/bin/env python3
"""
File operations tool - read, write, edit, list files and directories.
Provides Claude Code-like file access capabilities.
"""

import sys
import json
import os
from pathlib import Path


def read_file(file_path: str, offset: int = 0, limit: int = 2000) -> dict:
    """Read a file and return its contents."""
    try:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        if not path.is_file():
            return {"error": f"Not a file: {file_path}"}

        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)
        selected_lines = lines[offset:offset + limit]

        # Add line numbers
        numbered_lines = []
        for i, line in enumerate(selected_lines, start=offset + 1):
            numbered_lines.append(f"{i:6}\t{line.rstrip()}")

        return {
            "content": "\n".join(numbered_lines),
            "total_lines": total_lines,
            "showing": f"lines {offset + 1}-{min(offset + limit, total_lines)} of {total_lines}",
            "file_path": str(path.absolute())
        }
    except Exception as e:
        return {"error": str(e)}


def write_file(file_path: str, content: str) -> dict:
    """Write content to a file (creates or overwrites)."""
    try:
        path = Path(file_path)

        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

        return {
            "success": True,
            "message": f"File written: {file_path}",
            "bytes_written": len(content.encode('utf-8'))
        }
    except Exception as e:
        return {"error": str(e)}


def edit_file(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
    """Edit a file by replacing old_string with new_string."""
    try:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        if old_string not in content:
            return {"error": f"old_string not found in file"}

        count = content.count(old_string)
        if count > 1 and not replace_all:
            return {
                "error": f"old_string found {count} times. Set replace_all=true to replace all, or provide more context to make it unique."
            }

        if replace_all:
            new_content = content.replace(old_string, new_string)
            replaced = count
        else:
            new_content = content.replace(old_string, new_string, 1)
            replaced = 1

        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return {
            "success": True,
            "message": f"Replaced {replaced} occurrence(s) in {file_path}",
            "replacements": replaced
        }
    except Exception as e:
        return {"error": str(e)}


def list_directory(dir_path: str = ".", pattern: str = None) -> dict:
    """List files and directories in a path."""
    try:
        path = Path(dir_path)
        if not path.exists():
            return {"error": f"Directory not found: {dir_path}"}

        if not path.is_dir():
            return {"error": f"Not a directory: {dir_path}"}

        items = []
        for item in sorted(path.iterdir()):
            stat = item.stat()
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else None,
                "path": str(item.absolute())
            })

        # Filter by pattern if provided
        if pattern:
            import fnmatch
            items = [i for i in items if fnmatch.fnmatch(i["name"], pattern)]

        return {
            "directory": str(path.absolute()),
            "count": len(items),
            "items": items
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action parameter",
            "usage": "file_ops.py <action> [params]",
            "actions": ["read", "write", "edit", "list"]
        }))
        sys.exit(1)

    action = sys.argv[1]

    # Parse JSON params from stdin or remaining args
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            # Try to parse as key=value pairs
            for arg in sys.argv[2:]:
                if '=' in arg:
                    key, value = arg.split('=', 1)
                    params[key] = value

    if action == "read":
        file_path = params.get("file_path") or params.get("path")
        if not file_path:
            print(json.dumps({"error": "file_path is required"}))
            sys.exit(1)
        result = read_file(
            file_path,
            offset=int(params.get("offset", 0)),
            limit=int(params.get("limit", 2000))
        )

    elif action == "write":
        file_path = params.get("file_path") or params.get("path")
        content = params.get("content")
        if not file_path or content is None:
            print(json.dumps({"error": "file_path and content are required"}))
            sys.exit(1)
        result = write_file(file_path, content)

    elif action == "edit":
        file_path = params.get("file_path") or params.get("path")
        old_string = params.get("old_string")
        new_string = params.get("new_string")
        if not all([file_path, old_string is not None, new_string is not None]):
            print(json.dumps({"error": "file_path, old_string, and new_string are required"}))
            sys.exit(1)
        result = edit_file(
            file_path,
            old_string,
            new_string,
            replace_all=params.get("replace_all", False)
        )

    elif action == "list":
        dir_path = params.get("dir_path") or params.get("path", ".")
        result = list_directory(dir_path, pattern=params.get("pattern"))

    else:
        result = {"error": f"Unknown action: {action}", "actions": ["read", "write", "edit", "list"]}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
