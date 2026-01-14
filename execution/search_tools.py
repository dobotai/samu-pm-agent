#!/usr/bin/env python3
"""
Search tools - glob pattern matching and grep content search.
Provides Claude Code-like search capabilities.
"""

import sys
import json
import os
import re
from pathlib import Path
import fnmatch


def glob_search(pattern: str, path: str = ".", max_results: int = 100) -> dict:
    """Find files matching a glob pattern."""
    try:
        base_path = Path(path).resolve()

        if not base_path.exists():
            return {"error": f"Path not found: {path}"}

        matches = []

        # Handle ** patterns for recursive search
        if "**" in pattern:
            for file_path in base_path.rglob(pattern.replace("**/", "")):
                if len(matches) >= max_results:
                    break
                try:
                    stat = file_path.stat()
                    matches.append({
                        "path": str(file_path),
                        "relative": str(file_path.relative_to(base_path)),
                        "size": stat.st_size if file_path.is_file() else None,
                        "type": "file" if file_path.is_file() else "directory"
                    })
                except (OSError, PermissionError):
                    continue
        else:
            # Non-recursive glob
            for file_path in base_path.glob(pattern):
                if len(matches) >= max_results:
                    break
                try:
                    stat = file_path.stat()
                    matches.append({
                        "path": str(file_path),
                        "relative": str(file_path.relative_to(base_path)),
                        "size": stat.st_size if file_path.is_file() else None,
                        "type": "file" if file_path.is_file() else "directory"
                    })
                except (OSError, PermissionError):
                    continue

        # Sort by modification time (most recent first)
        matches.sort(key=lambda x: Path(x["path"]).stat().st_mtime if Path(x["path"]).exists() else 0, reverse=True)

        return {
            "pattern": pattern,
            "base_path": str(base_path),
            "count": len(matches),
            "truncated": len(matches) >= max_results,
            "matches": matches
        }

    except Exception as e:
        return {"error": str(e)}


def grep_search(
    pattern: str,
    path: str = ".",
    file_pattern: str = None,
    case_insensitive: bool = False,
    context_lines: int = 0,
    max_matches: int = 100
) -> dict:
    """Search for pattern in file contents."""
    try:
        base_path = Path(path).resolve()

        if not base_path.exists():
            return {"error": f"Path not found: {path}"}

        # Compile regex
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return {"error": f"Invalid regex pattern: {e}"}

        results = []
        files_searched = 0
        total_matches = 0

        # Determine files to search
        if base_path.is_file():
            files_to_search = [base_path]
        else:
            if file_pattern:
                files_to_search = list(base_path.rglob(file_pattern))
            else:
                # Search common text files
                text_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.md', '.txt',
                                   '.html', '.css', '.yaml', '.yml', '.toml', '.ini', '.cfg',
                                   '.sh', '.bash', '.zsh', '.env', '.gitignore', '.sql'}
                files_to_search = [
                    f for f in base_path.rglob("*")
                    if f.is_file() and (f.suffix.lower() in text_extensions or not f.suffix)
                ]

        for file_path in files_to_search:
            if total_matches >= max_matches:
                break

            if not file_path.is_file():
                continue

            # Skip binary files and large files
            try:
                if file_path.stat().st_size > 1_000_000:  # Skip files > 1MB
                    continue
            except (OSError, PermissionError):
                continue

            files_searched += 1

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines):
                    if regex.search(line):
                        total_matches += 1
                        if total_matches > max_matches:
                            break

                        match_info = {
                            "file": str(file_path),
                            "relative": str(file_path.relative_to(base_path)) if base_path in file_path.parents or base_path == file_path else str(file_path),
                            "line_number": i + 1,
                            "line": line.rstrip()[:500]  # Limit line length
                        }

                        # Add context lines if requested
                        if context_lines > 0:
                            start = max(0, i - context_lines)
                            end = min(len(lines), i + context_lines + 1)
                            match_info["context"] = [
                                {"line_number": j + 1, "content": lines[j].rstrip()[:500]}
                                for j in range(start, end)
                            ]

                        results.append(match_info)

            except (OSError, PermissionError, UnicodeDecodeError):
                continue

        return {
            "pattern": pattern,
            "base_path": str(base_path),
            "files_searched": files_searched,
            "match_count": len(results),
            "truncated": total_matches > max_matches,
            "matches": results
        }

    except Exception as e:
        return {"error": str(e)}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action parameter",
            "usage": "search_tools.py <action> <params_json>",
            "actions": ["glob", "grep"]
        }))
        sys.exit(1)

    action = sys.argv[1]

    # Parse JSON params
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            # For simple cases
            if action == "glob":
                params = {"pattern": sys.argv[2]}
            elif action == "grep":
                params = {"pattern": sys.argv[2]}

    if action == "glob":
        pattern = params.get("pattern")
        if not pattern:
            print(json.dumps({"error": "pattern is required"}))
            sys.exit(1)
        result = glob_search(
            pattern,
            path=params.get("path", "."),
            max_results=int(params.get("max_results", 100))
        )

    elif action == "grep":
        pattern = params.get("pattern")
        if not pattern:
            print(json.dumps({"error": "pattern is required"}))
            sys.exit(1)
        result = grep_search(
            pattern,
            path=params.get("path", "."),
            file_pattern=params.get("file_pattern"),
            case_insensitive=params.get("case_insensitive", False),
            context_lines=int(params.get("context_lines", 0)),
            max_matches=int(params.get("max_matches", 100))
        )

    else:
        result = {"error": f"Unknown action: {action}", "actions": ["glob", "grep"]}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
