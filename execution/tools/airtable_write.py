#!/usr/bin/env python3
"""
Airtable Write Tool
Create and update Airtable records with approval safeguards
"""

import json
import os
import sys
import requests


# SAFETY LIMITS - Require approval for operations exceeding these
MAX_RECORDS_WITHOUT_APPROVAL = 5
MAX_BULK_DELETE_WITHOUT_APPROVAL = 3


def get_airtable_headers():
    """Get authorization headers for Airtable API"""
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise Exception("AIRTABLE_API_KEY not found in environment variables")

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }


def main():
    """Write operations to Airtable with safety guardrails"""

    # Parse input arguments
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action parameter. Usage: airtable_write.py <action> [params]"
        }))
        sys.exit(1)

    action = sys.argv[1]

    try:
        headers = get_airtable_headers()

        if action == "create_record":
            # Create a single record
            if len(sys.argv) < 5:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_write.py create_record <base_id> <table_name> <fields_json>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]
            fields_json = sys.argv[4]
            fields = json.loads(fields_json)

            url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
            payload = {"fields": fields}

            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()

            record = response.json()

            print(json.dumps({
                "success": True,
                "message": "Record created successfully",
                "record_id": record["id"],
                "fields": record.get("fields", {})
            }))

        elif action == "update_record":
            # Update a single record
            if len(sys.argv) < 6:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_write.py update_record <base_id> <table_name> <record_id> <fields_json>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]
            record_id = sys.argv[4]
            fields_json = sys.argv[5]
            fields = json.loads(fields_json)

            url = f"https://api.airtable.com/v0/{base_id}/{table_name}/{record_id}"
            payload = {"fields": fields}

            response = requests.patch(url, headers=headers, json=payload)
            response.raise_for_status()

            record = response.json()

            print(json.dumps({
                "success": True,
                "message": "Record updated successfully",
                "record_id": record["id"],
                "fields": record.get("fields", {})
            }))

        elif action == "delete_record":
            # Delete a single record
            if len(sys.argv) < 5:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_write.py delete_record <base_id> <table_name> <record_id>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]
            record_id = sys.argv[4]

            url = f"https://api.airtable.com/v0/{base_id}/{table_name}/{record_id}"

            response = requests.delete(url, headers=headers)
            response.raise_for_status()

            print(json.dumps({
                "success": True,
                "message": "Record deleted successfully",
                "record_id": record_id,
                "warning": "⚠️ This action cannot be undone"
            }))

        elif action == "bulk_create":
            # Create multiple records - REQUIRES APPROVAL if count > MAX_RECORDS_WITHOUT_APPROVAL
            if len(sys.argv) < 5:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_write.py bulk_create <base_id> <table_name> <records_json>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]
            records_json = sys.argv[4]
            records = json.loads(records_json)

            # Safety check
            if len(records) > MAX_RECORDS_WITHOUT_APPROVAL:
                print(json.dumps({
                    "approval_required": True,
                    "action": "bulk_create",
                    "record_count": len(records),
                    "limit": MAX_RECORDS_WITHOUT_APPROVAL,
                    "message": f"⚠️ APPROVAL REQUIRED: Attempting to create {len(records)} records (limit: {MAX_RECORDS_WITHOUT_APPROVAL})",
                    "instructions": "Please confirm this bulk operation before proceeding."
                }))
                sys.exit(0)

            url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
            payload = {"records": [{"fields": rec} for rec in records]}

            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()

            created_records = response.json()

            print(json.dumps({
                "success": True,
                "message": f"Created {len(created_records['records'])} records successfully",
                "record_count": len(created_records['records']),
                "record_ids": [r["id"] for r in created_records["records"]]
            }))

        elif action == "bulk_update":
            # Update multiple records - REQUIRES APPROVAL if count > MAX_RECORDS_WITHOUT_APPROVAL
            if len(sys.argv) < 5:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_write.py bulk_update <base_id> <table_name> <updates_json>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]
            updates_json = sys.argv[4]
            updates = json.loads(updates_json)  # Format: [{"id": "recXXX", "fields": {...}}, ...]

            # Safety check
            if len(updates) > MAX_RECORDS_WITHOUT_APPROVAL:
                print(json.dumps({
                    "approval_required": True,
                    "action": "bulk_update",
                    "record_count": len(updates),
                    "limit": MAX_RECORDS_WITHOUT_APPROVAL,
                    "message": f"⚠️ APPROVAL REQUIRED: Attempting to update {len(updates)} records (limit: {MAX_RECORDS_WITHOUT_APPROVAL})",
                    "instructions": "Please confirm this bulk operation before proceeding."
                }))
                sys.exit(0)

            url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
            payload = {"records": updates}

            response = requests.patch(url, headers=headers, json=payload)
            response.raise_for_status()

            updated_records = response.json()

            print(json.dumps({
                "success": True,
                "message": f"Updated {len(updated_records['records'])} records successfully",
                "record_count": len(updated_records['records']),
                "record_ids": [r["id"] for r in updated_records["records"]]
            }))

        elif action == "bulk_delete":
            # Delete multiple records - REQUIRES APPROVAL if count > MAX_BULK_DELETE_WITHOUT_APPROVAL
            if len(sys.argv) < 5:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_write.py bulk_delete <base_id> <table_name> <record_ids_json>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]
            record_ids_json = sys.argv[4]
            record_ids = json.loads(record_ids_json)

            # Safety check - stricter limit for deletions
            if len(record_ids) > MAX_BULK_DELETE_WITHOUT_APPROVAL:
                print(json.dumps({
                    "approval_required": True,
                    "action": "bulk_delete",
                    "record_count": len(record_ids),
                    "limit": MAX_BULK_DELETE_WITHOUT_APPROVAL,
                    "message": f"⚠️ APPROVAL REQUIRED: Attempting to DELETE {len(record_ids)} records (limit: {MAX_BULK_DELETE_WITHOUT_APPROVAL})",
                    "warning": "This action CANNOT be undone!",
                    "instructions": "Please confirm this bulk deletion before proceeding."
                }))
                sys.exit(0)

            url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
            params = {"records[]": record_ids}

            response = requests.delete(url, headers=headers, params=params)
            response.raise_for_status()

            deleted_records = response.json()

            print(json.dumps({
                "success": True,
                "message": f"Deleted {len(deleted_records['records'])} records successfully",
                "record_count": len(deleted_records['records']),
                "warning": "⚠️ This action cannot be undone"
            }))

        else:
            print(json.dumps({
                "error": f"Unknown action: {action}",
                "available_actions": [
                    "create_record",
                    "update_record",
                    "delete_record",
                    "bulk_create",
                    "bulk_update",
                    "bulk_delete"
                ]
            }))
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        print(json.dumps({
            "error": f"Airtable API error: {str(e)}"
        }))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "error": f"Unexpected error: {str(e)}"
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
