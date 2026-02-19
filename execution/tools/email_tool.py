#!/usr/bin/env python3
"""
SendGrid Email - Send emails via SendGrid API.

Credential-ready: works when SENDGRID_API_KEY and SENDGRID_FROM_EMAIL are set.

Actions:
    send_email          - Send a plain text or HTML email
    send_template_email - Send using a SendGrid dynamic template

Usage:
    python email_tool.py send_email '{"to": "client@example.com", "subject": "Update", "body": "..."}'
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


def _check_credentials():
    """Return error dict if credentials missing."""
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("SENDGRID_FROM_EMAIL")

    if not api_key:
        return {"success": False, "error": "SENDGRID_API_KEY not set in .env"}
    if not from_email:
        return {"success": False, "error": "SENDGRID_FROM_EMAIL not set in .env"}
    return None


def send_email(to: str, subject: str, body: str, html: bool = False,
               cc: str = None, reply_to: str = None) -> dict:
    """Send a plain text or HTML email via SendGrid."""
    err = _check_credentials()
    if err:
        return err

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Email, To, Content, Cc, ReplyTo
    except ImportError:
        return {"success": False, "error": "sendgrid package not installed"}

    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("SENDGRID_FROM_EMAIL")

    content_type = "text/html" if html else "text/plain"

    message = Mail(
        from_email=Email(from_email),
        to_emails=To(to),
        subject=subject,
        plain_text_content=Content(content_type, body) if not html else None,
        html_content=Content(content_type, body) if html else None,
    )

    if cc:
        message.add_cc(Cc(cc))

    if reply_to:
        message.reply_to = ReplyTo(reply_to)

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)

        return {
            "success": True,
            "status_code": response.status_code,
            "to": to,
            "subject": subject,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_template_email(to: str, template_id: str,
                         dynamic_data: dict = None) -> dict:
    """Send email using a SendGrid dynamic template."""
    err = _check_credentials()
    if err:
        return err

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Email, To
    except ImportError:
        return {"success": False, "error": "sendgrid package not installed"}

    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("SENDGRID_FROM_EMAIL")

    message = Mail(
        from_email=Email(from_email),
        to_emails=To(to),
    )
    message.template_id = template_id
    if dynamic_data:
        message.dynamic_template_data = dynamic_data

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)

        return {
            "success": True,
            "status_code": response.status_code,
            "to": to,
            "template_id": template_id,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: email_tool.py <action> '<json_params>'"}))
        sys.exit(1)

    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON params"}))
            sys.exit(1)

    if action == "send_email":
        result = send_email(
            to=params["to"],
            subject=params["subject"],
            body=params["body"],
            html=params.get("html", False),
            cc=params.get("cc"),
            reply_to=params.get("reply_to"),
        )
    elif action == "send_template_email":
        result = send_template_email(
            to=params["to"],
            template_id=params["template_id"],
            dynamic_data=params.get("dynamic_data"),
        )
    else:
        result = {"error": f"Unknown action: {action}"}
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
