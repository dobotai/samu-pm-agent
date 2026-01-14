#!/usr/bin/env python3
"""
Request Approval Tool
Request human approval before making significant changes
"""

import json
import os
import sys
from datetime import datetime


def main():
    """Request approval for an action"""

    # Parse input arguments
    if len(sys.argv) < 3:
        print(json.dumps({
            "error": "Missing parameters. Usage: request_approval.py <action_type> <action_details>"
        }))
        sys.exit(1)

    action_type = sys.argv[1]
    action_details = sys.argv[2]

    # Log the approval request
    log_dir = ".tmp/logs"
    os.makedirs(log_dir, exist_ok=True)

    approval_request = {
        "timestamp": datetime.now().isoformat(),
        "action_type": action_type,
        "action_details": action_details,
        "status": "pending_approval"
    }

    log_file = os.path.join(log_dir, "approval_requests.jsonl")
    with open(log_file, "a") as f:
        f.write(json.dumps(approval_request) + "\n")

    # Return approval request to user
    print(json.dumps({
        "approval_required": True,
        "action_type": action_type,
        "details": action_details,
        "message": f"⚠️ APPROVAL REQUIRED: The agent wants to {action_type}. Details: {action_details}",
        "instructions": "Please review this action and confirm if you want to proceed. The agent will wait for your approval."
    }))


if __name__ == "__main__":
    main()
