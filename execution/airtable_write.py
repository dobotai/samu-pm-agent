#!/usr/bin/env python3
"""
Airtable Write Tool - Creates new records in an Airtable table
Part of DOEBI execution layer (deterministic tool)

Usage:
    python airtable_write.py <table_name> <fields_json>

Examples:
    python airtable_write.py "Tasks" '{"Title": "New Task", "Status": "To Do"}'
    python airtable_write.py "Projects" '{"Name": "Q1 Campaign", "Owner": "Sarah"}'
"""

import os
import sys
import json
import argparse
from pyairtable import Api
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_airtable_record(table_name, fields):
    """
    Create a new record in an Airtable table

    Args:
        table_name: Name of the table to create record in
        fields: Dictionary of field names and values

    Returns:
        Created record with ID
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

    # Create record
    record = table.create(fields)

    return {
        'id': record['id'],
        'created_time': record.get('createdTime'),
        'fields': record['fields']
    }

def main():
    parser = argparse.ArgumentParser(
        description='Create a new record in an Airtable table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Tasks" '{"Title": "New Task", "Status": "To Do"}'
  %(prog)s "Projects" '{"Name": "Q1 Campaign", "Owner": "Sarah"}'
        """
    )

    parser.add_argument('table_name', help='Name of the Airtable table')
    parser.add_argument('fields_json', help='JSON object with field names and values')

    args = parser.parse_args()

    try:
        # Parse fields JSON
        fields = json.loads(args.fields_json)

        # Create record
        record = create_airtable_record(args.table_name, fields)

        # Output result
        print(json.dumps(record, indent=2))
        print(f"\nSuccess! Created record with ID: {record['id']}", file=sys.stderr)

        return 0

    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON - {str(e)}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
