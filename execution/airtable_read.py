#!/usr/bin/env python3
"""
Airtable Read Tool - Pulls records from any table in an Airtable base
Part of DOEBI execution layer (deterministic tool)

Usage:
    python airtable_read.py <table_name> [--filter <formula>] [--fields <field1,field2>] [--max-records <num>]

Examples:
    python airtable_read.py "Projects"
    python airtable_read.py "Tasks" --filter "Status='In Progress'"
    python airtable_read.py "Videos" --fields "Title,Status,Due Date" --max-records 50
"""

import os
import sys
import json
import argparse
from pyairtable import Api
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def read_airtable_records(table_name, filter_formula=None, fields=None, max_records=None):
    """
    Read records from an Airtable table

    Args:
        table_name: Name of the table to read from
        filter_formula: Optional Airtable formula for filtering (e.g., "Status='Active'")
        fields: Optional list of field names to return (returns all if None)
        max_records: Optional maximum number of records to return

    Returns:
        List of records with their fields
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

    # Build query parameters
    kwargs = {}
    if filter_formula:
        kwargs['formula'] = filter_formula
    if fields:
        kwargs['fields'] = fields
    if max_records:
        kwargs['max_records'] = max_records

    # Fetch records
    records = table.all(**kwargs)

    # Format records for output
    formatted_records = []
    for record in records:
        formatted_records.append({
            'id': record['id'],
            'created_time': record.get('createdTime'),
            'fields': record['fields']
        })

    return formatted_records

def main():
    parser = argparse.ArgumentParser(
        description='Read records from an Airtable table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Projects"
  %(prog)s "Tasks" --filter "Status='In Progress'"
  %(prog)s "Videos" --fields "Title,Status,Due Date" --max-records 50
        """
    )

    parser.add_argument('table_name', help='Name of the Airtable table to read from')
    parser.add_argument('--filter', dest='filter_formula', help='Airtable formula for filtering records')
    parser.add_argument('--fields', help='Comma-separated list of fields to return')
    parser.add_argument('--max-records', type=int, help='Maximum number of records to return')
    parser.add_argument('--output', choices=['json', 'summary'], default='json',
                       help='Output format (default: json)')

    args = parser.parse_args()

    try:
        # Parse fields if provided
        fields_list = None
        if args.fields:
            fields_list = [f.strip() for f in args.fields.split(',')]

        # Read records
        records = read_airtable_records(
            table_name=args.table_name,
            filter_formula=args.filter_formula,
            fields=fields_list,
            max_records=args.max_records
        )

        # Output results
        if args.output == 'json':
            print(json.dumps(records, indent=2))
        else:
            # Summary output
            print(f"Found {len(records)} records in table '{args.table_name}'")
            if records:
                print("\nSample record fields:")
                for key in list(records[0]['fields'].keys())[:10]:
                    print(f"  - {key}")
                if len(records[0]['fields']) > 10:
                    print(f"  ... and {len(records[0]['fields']) - 10} more fields")

        return 0

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
