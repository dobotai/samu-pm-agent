#!/usr/bin/env python3
"""
Airtable Read Tool
Access information from Airtable bases and tables
"""

import json
import os
import sys
import requests


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
    """Read information from Airtable"""

    # Parse input arguments
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action parameter. Usage: airtable_read.py <action> [params]"
        }))
        sys.exit(1)

    action = sys.argv[1]

    try:
        headers = get_airtable_headers()

        if action == "list_records":
            # List records from a specific table
            if len(sys.argv) < 4:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_read.py list_records <base_id> <table_name>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]
            limit = int(sys.argv[4]) if len(sys.argv) > 4 else 100

            url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
            params = {"maxRecords": limit}

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            records = []

            for record in data.get("records", []):
                records.append({
                    "id": record["id"],
                    "created_time": record.get("createdTime", ""),
                    "fields": record.get("fields", {})
                })

            print(json.dumps({
                "records": records,
                "count": len(records),
                "base_id": base_id,
                "table_name": table_name
            }))

        elif action == "get_record":
            # Get a specific record by ID
            if len(sys.argv) < 4:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_read.py get_record <base_id> <table_name> <record_id>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]
            record_id = sys.argv[4]

            url = f"https://api.airtable.com/v0/{base_id}/{table_name}/{record_id}"

            response = requests.get(url, headers=headers)
            response.raise_for_status()

            record = response.json()

            print(json.dumps({
                "id": record["id"],
                "created_time": record.get("createdTime", ""),
                "fields": record.get("fields", {})
            }))

        elif action == "search_records":
            # Search records with a filter formula
            if len(sys.argv) < 4:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_read.py search_records <base_id> <table_name> <field_name> <search_value>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]
            field_name = sys.argv[4]
            search_value = sys.argv[5] if len(sys.argv) > 5 else ""

            # Build Airtable filter formula
            filter_formula = f"SEARCH(LOWER('{search_value}'), LOWER({{{field_name}}}))"

            url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
            params = {
                "filterByFormula": filter_formula,
                "maxRecords": 50
            }

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            records = []

            for record in data.get("records", []):
                records.append({
                    "id": record["id"],
                    "created_time": record.get("createdTime", ""),
                    "fields": record.get("fields", {})
                })

            print(json.dumps({
                "records": records,
                "count": len(records),
                "search_field": field_name,
                "search_value": search_value
            }))

        elif action == "filter_records":
            # Filter records with custom formula
            if len(sys.argv) < 4:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_read.py filter_records <base_id> <table_name> <filter_formula>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]
            filter_formula = sys.argv[4]

            url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
            params = {
                "filterByFormula": filter_formula,
                "maxRecords": 100
            }

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            records = []

            for record in data.get("records", []):
                records.append({
                    "id": record["id"],
                    "created_time": record.get("createdTime", ""),
                    "fields": record.get("fields", {})
                })

            print(json.dumps({
                "records": records,
                "count": len(records),
                "filter": filter_formula
            }))

        elif action == "list_bases":
            # List all bases (requires meta API access)
            url = "https://api.airtable.com/v0/meta/bases"

            response = requests.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            bases = []

            for base in data.get("bases", []):
                bases.append({
                    "id": base["id"],
                    "name": base["name"],
                    "permission_level": base.get("permissionLevel", "")
                })

            print(json.dumps({
                "bases": bases,
                "count": len(bases)
            }))

        elif action == "get_table_schema":
            # Get schema information for a table
            if len(sys.argv) < 3:
                print(json.dumps({
                    "error": "Missing parameters. Usage: airtable_read.py get_table_schema <base_id> <table_name>"
                }))
                sys.exit(1)

            base_id = sys.argv[2]
            table_name = sys.argv[3]

            # Get a single record to extract field names
            url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
            params = {"maxRecords": 1}

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            records = data.get("records", [])

            if records:
                fields = list(records[0].get("fields", {}).keys())
                print(json.dumps({
                    "table_name": table_name,
                    "fields": fields,
                    "field_count": len(fields)
                }))
            else:
                print(json.dumps({
                    "table_name": table_name,
                    "fields": [],
                    "field_count": 0,
                    "note": "No records found in table"
                }))

        else:
            print(json.dumps({
                "error": f"Unknown action: {action}",
                "available_actions": ["list_records", "get_record", "search_records", "filter_records", "list_bases", "get_table_schema"]
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
