#!/usr/bin/env python3
"""
Airtable Update Tool - Updates existing records in an Airtable table
Part of DOEBI execution layer (deterministic tool)

Usage:
    python airtable_update.py <table_name> <record_id> <fields_json>

Examples:
    python airtable_update.py "Tasks" "rec123456" '{"Status": "Done"}'
    python airtable_update.py "Projects" "recABC789" '{"Status": "Active", "Progress": 75}'
"""

import os
import sys
import json
import argparse
from pyairtable import Api
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def update_airtable_record(table_name, record_id, fields):
    """
    Update an existing record in an Airtable table

    Args:
        table_name: Name of the table
        record_id: ID of the record to update
        fields: Dictionary of field names and values to update

    Returns:
        Updated record
    """
    # Get credentials from environment
    api_key = os.getenv('AIRTABLE_API_KEY')
    base_id = os.getenv('AIRTABLE_BASE_ID')

    if not api_key:
        raise ValueError("AIRTABLE_API_KEY not found in environment variables")
    if not base_id:
        raise ValueError("AIRTABLE_BASE_ID not found in environment variables")

    # Initialize Airtable API
    api = Api(api_key)
    table = api.table(base_id, table_name)

    # Update record
    record = table.update(record_id, fields)

    return {
        'id': record['id'],
        'fields': record['fields']
    }

def main():
    parser = argparse.ArgumentParser(
        description='Update an existing record in an Airtable table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Tasks" "rec123456" '{"Status": "Done"}'
  %(prog)s "Projects" "recABC789" '{"Status": "Active", "Progress": 75}'
        """
    )

    parser.add_argument('table_name', help='Name of the Airtable table')
    parser.add_argument('record_id', help='ID of the record to update (starts with "rec")')
    parser.add_argument('fields_json', help='JSON object with field names and values to update')

    args = parser.parse_args()

    try:
        # Parse fields JSON
        fields = json.loads(args.fields_json)

        # Update record
        record = update_airtable_record(args.table_name, args.record_id, fields)

        # Output result
        print(json.dumps(record, indent=2))
        print(f"\nSuccess! Updated record {record['id']}", file=sys.stderr)

        return 0

    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON - {str(e)}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
