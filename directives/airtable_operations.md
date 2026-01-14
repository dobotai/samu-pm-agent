# Airtable Operations - KS Media Base

## Overview
Standard operating procedures for interacting with the KS Media Airtable base. The base contains 4 tables: Team, Clients, Videos, and SOP Bank.

**Base ID:** `apph2RxHbsyqmCwxk`
**Authentication:** Personal Access Token stored in `.env` as `AIRTABLE_API_KEY`

## Available Tables

1. **Team** (10 fields, ~22 records)
   - Team member information
   - Fields: Name, Slack ID, Role, Email, Videos assigned

2. **Clients** (67 fields)
   - Client information and project details
   - Extensive metadata for client management

3. **Videos** (42 fields)
   - Video production tracking
   - Fields: Video ID, Client, Format, Editing Status, Assigned Editor, Deadlines, etc.

4. **SOP Bank** (9 fields)
   - Standard operating procedures repository

## Tools Available

### 1. List All Tables
**Script:** `execution/airtable_list_tables.py`

**Purpose:** Discover all tables in the base and their field structures

**Usage:**
```bash
# Simple list
python execution/airtable_list_tables.py

# Detailed with field schemas
python execution/airtable_list_tables.py --detailed

# JSON output
python execution/airtable_list_tables.py --output json
```

**When to use:**
- First time exploring the base
- Checking available fields before creating/updating records
- Understanding data structure

### 2. Read Records
**Script:** `execution/airtable_read.py`

**Purpose:** Retrieve records from any table with optional filtering

**Usage:**
```bash
# Get all records from a table
python execution/airtable_read.py "Videos"

# Filter records (Airtable formula syntax)
python execution/airtable_read.py "Videos" --filter "Editing Status='100 - Scheduled - DONE'"

# Get specific fields only
python execution/airtable_read.py "Team" --fields "Name,Role,Email"

# Limit number of records
python execution/airtable_read.py "Videos" --max-records 10

# Get summary instead of full JSON
python execution/airtable_read.py "Clients" --output summary
```

**Airtable Filter Examples:**
- Single condition: `Status='Active'`
- Multiple conditions: `AND(Status='Active', {Assigned Editor}='Sarah')`
- Date comparison: `Deadline<TODAY()`
- Contains: `SEARCH('urgent', Notes)>0`

**Output:** JSON array of records with `id`, `created_time`, and `fields`

**When to use:**
- Checking current status of videos
- Finding records by specific criteria
- Generating reports
- Syncing data to other systems

### 3. Create Records
**Script:** `execution/airtable_write.py`

**Purpose:** Add new records to a table

**Usage:**
```bash
# Create a new video record
python execution/airtable_write.py "Videos" '{"Video ID": 1801, "Client": ["recXXX"], "Format": "Long-Form"}'

# Create a team member
python execution/airtable_write.py "Team" '{"Name": "John Doe", "Role": "Editor", "Email": "john@example.com"}'
```

**Important Notes:**
- Field names must match exactly (case-sensitive)
- Linked records (like Client) require record IDs in array format: `["recXXX"]`
- Use proper JSON formatting with escaped quotes
- Some fields may be auto-calculated and should not be set manually

**Output:** Created record with its new ID

**When to use:**
- Adding new videos to the pipeline
- Onboarding new team members
- Creating new client records
- Logging new SOPs

### 4. Update Records
**Script:** `execution/airtable_update.py`

**Purpose:** Modify existing records

**Usage:**
```bash
# Update video status
python execution/airtable_update.py "Videos" "rec013vsfYaTVbATk" '{"Editing Status": "50 - First Draft Complete"}'

# Assign editor to video
python execution/airtable_update.py "Videos" "recXXX" '{"Assigned Editor": ["rec73fQu0xxq4F9Df"]}'

# Update multiple fields
python execution/airtable_update.py "Videos" "recXXX" '{"Editing Status": "Done", "Thumbnail Status": "Approved"}'
```

**Important Notes:**
- Record ID (starts with `rec`) is required
- Only include fields you want to change
- Linked records must be in array format
- Validation rules in Airtable still apply

**Output:** Updated record with all current field values

**When to use:**
- Updating video progress/status
- Changing assignments
- Marking deadlines
- Correcting errors

## Common Workflows

### Workflow 1: Check Video Pipeline Status
**Goal:** See all videos currently in progress

```bash
# Get videos not yet completed
python execution/airtable_read.py "Videos" \
  --filter "NOT(Editing Status='100 - Scheduled - DONE')" \
  --fields "Video ID,Client,Editing Status,Assigned Editor,Deadline" \
  --max-records 50
```

### Workflow 2: Find Videos Assigned to Specific Editor
**Goal:** See all videos for a team member

```bash
# First get the editor's record ID from Team table
python execution/airtable_read.py "Team" \
  --filter "Name='Ananda'" \
  --fields "Name,rec id"

# Then use that ID to filter Videos
python execution/airtable_read.py "Videos" \
  --filter "FIND('rec73fQu0xxq4F9Df', ARRAYJOIN({Assigned Editor}))" \
  --fields "Video ID,Editing Status,Deadline"
```

### Workflow 3: Update Video to Next Stage
**Goal:** Move video through the production pipeline

```bash
# Update status when draft is complete
python execution/airtable_update.py "Videos" "recXXX" \
  '{"Editing Status": "50 - First Draft Complete"}'

# Update when thumbnail is approved
python execution/airtable_update.py "Videos" "recXXX" \
  '{"Thumbnail Status": "Thumbnail Approved"}'
```

### Workflow 4: Get All Videos for a Client
**Goal:** See production status for specific client

```bash
# First get client's record ID
python execution/airtable_read.py "Clients" --output summary

# Then filter videos by client
python execution/airtable_read.py "Videos" \
  --filter "FIND('rec2TTPeqjcygT0Lz', ARRAYJOIN(Client))" \
  --fields "Video ID,Video Number,Editing Status,Deadline"
```

## Error Handling

### Common Errors

**"Field name not found"**
- Check exact field name spelling and capitalization
- Use `airtable_list_tables.py --detailed` to see all field names

**"Invalid record ID"**
- Ensure record ID starts with `rec`
- Verify record exists in the table
- Check you're querying the correct table

**"Invalid filter formula"**
- Test formulas in Airtable UI first
- Use proper Airtable formula syntax
- Escape special characters in bash

**"Authentication failed"**
- Verify `AIRTABLE_API_KEY` in `.env`
- Check token has appropriate scopes
- Ensure token hasn't expired

### Self-Annealing Notes

**API Rate Limits:**
- Airtable allows 5 requests per second per base
- If hitting limits, add delay between calls
- Consider batching operations

**Field Types to Watch:**
- Linked records must use record IDs, not display names
- Date fields need ISO format: `YYYY-MM-DD`
- Checkboxes are boolean: `true`/`false`
- Multi-select fields are arrays: `["Option1", "Option2"]`

**Performance Tips:**
- Use `--fields` to limit returned data
- Use `--max-records` for large tables
- Filter server-side rather than locally
- Cache table schemas to avoid repeated metadata calls

## Integration Opportunities

**Future Tool Ideas:**
- Slack integration: Post updates when video status changes
- Google Sheets sync: Export reports to sheets
- Automated deadline reminders
- Batch status updates
- Video assignment balancing across editors
- Client progress reports

## Environment Variables Required

```env
AIRTABLE_API_KEY=patXXXXXXXXXXXXXX
AIRTABLE_BASE_ID=apph2RxHbsyqmCwxk
```

## Testing Checklist

- [ ] Can list all tables
- [ ] Can read records from each table
- [ ] Can filter records correctly
- [ ] Can create new records with required fields
- [ ] Can update existing records
- [ ] Error messages are clear and actionable
- [ ] JSON output is valid and parseable

## Learnings Log

*Document discoveries and edge cases here as you encounter them*

- Videos table has 42 fields including complex linked records
- Editor assignments link to Team table via record IDs
- Some videos have non-numeric Video Numbers (e.g., "podcast 1")
- Editing Status follows specific workflow stages (30, 50, 100)
