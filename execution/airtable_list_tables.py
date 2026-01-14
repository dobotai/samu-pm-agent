#!/usr/bin/env python3
"""
Airtable List Tables Tool - Lists all tables and their schemas in the base
Part of DOEBI execution layer (deterministic tool)

Usage:
    python airtable_list_tables.py [--detailed]

Examples:
    python airtable_list_tables.py
    python airtable_list_tables.py --detailed
"""

import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def list_airtable_tables(detailed=False):
    """
    List all tables in the Airtable base

    Args:
        detailed: If True, includes field schema information for each table

    Returns:
        List of tables with their metadata
    """
    # Get credentials from environment
    api_key = os.getenv('AIRTABLE_API_KEY')
    base_id = os.getenv('AIRTABLE_BASE_ID')

    if not api_key:
        raise ValueError("AIRTABLE_API_KEY not found in environment variables")
    if not base_id:
        raise ValueError("AIRTABLE_BASE_ID not found in environment variables")

    # Use Airtable Metadata API to get base schema
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    data = response.json()
    tables = data.get('tables', [])

    if not detailed:
        # Return simplified list
        return [{
            'id': table['id'],
            'name': table['name'],
            'primaryFieldId': table.get('primaryFieldId'),
            'field_count': len(table.get('fields', []))
        } for table in tables]
    else:
        # Return full schema
        return tables

def main():
    parser = argparse.ArgumentParser(
        description='List all tables in the Airtable base',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--detailed', action='store_true',
                       help='Include detailed field schema for each table')
    parser.add_argument('--output', choices=['json', 'summary'], default='summary',
                       help='Output format (default: summary)')

    args = parser.parse_args()

    try:
        # Get tables
        tables = list_airtable_tables(detailed=args.detailed)

        if args.output == 'json':
            print(json.dumps(tables, indent=2))
        else:
            # Summary output
            print(f"Found {len(tables)} tables in base:\n")
            for table in tables:
                print(f"- {table['name']}")
                if args.detailed and 'fields' in table:
                    print(f"   Fields ({len(table['fields'])}):")
                    for field in table['fields'][:10]:
                        field_type = field.get('type', 'unknown')
                        print(f"     - {field['name']} ({field_type})")
                    if len(table['fields']) > 10:
                        print(f"     ... and {len(table['fields']) - 10} more fields")
                elif not args.detailed and 'field_count' in table:
                    print(f"   Fields: {table['field_count']}")
                print()

        return 0

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
