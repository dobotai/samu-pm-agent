#!/usr/bin/env python3
"""
Example tool: Get current time
Simple demonstration of how execution tools work
"""

import json
from datetime import datetime


def main():
    """Get current date and time"""
    result = {
        "current_time": datetime.now().isoformat(),
        "formatted": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "Local"
    }

    # Tools must output JSON to stdout
    print(json.dumps(result))


if __name__ == "__main__":
    main()
