# Safety Guardrails Documentation

## Overview
This document describes the safety mechanisms implemented to prevent unauthorized or large-scale data changes in your YouTube agency project management agent.

## Safety Limits

### Slack Operations
- ✅ **Allowed without approval:**
  - Send individual messages to channels
  - Send individual DMs
  - Add reactions to messages
  - Reply to threads

- ⚠️ **Not implemented (would require approval):**
  - Bulk messaging to multiple channels
  - Mass DM campaigns
  - Channel deletion

### Airtable Operations

#### Single Record Operations (No approval needed)
- Create one record
- Update one record
- Delete one record (with warning)

#### Bulk Operations (Approval required when limits exceeded)

**Creation/Update Limit:** 5 records
- ✅ Create/update 1-5 records: Automatic
- ⚠️ Create/update 6+ records: **REQUIRES APPROVAL**

**Deletion Limit:** 3 records (stricter)
- ✅ Delete 1-3 records: Shows warning but proceeds
- ⚠️ Delete 4+ records: **REQUIRES APPROVAL**

## How Approval Works

When the agent attempts an operation that exceeds safety limits, it will:

1. **Stop execution** immediately
2. **Return an approval request** with:
   - Action type (e.g., "bulk_update")
   - Number of records affected
   - Details of what will change
   - Warning message
3. **Wait for human confirmation**
4. **Log the request** to `.tmp/logs/approval_requests.jsonl`

### Example Approval Response

```json
{
  "approval_required": true,
  "action": "bulk_update",
  "record_count": 15,
  "limit": 5,
  "message": "⚠️ APPROVAL REQUIRED: Attempting to update 15 records (limit: 5)",
  "instructions": "Please confirm this bulk operation before proceeding."
}
```

## System Constraints

The agent is configured with these explicit constraints (from `youtube_agency.json`):

1. ✅ Can read unlimited data from all sources
2. ✅ Can send individual messages
3. ⚠️ APPROVAL REQUIRED for:
   - Bulk Airtable operations (>5 records)
   - Bulk deletions (>3 records)
   - Operations affecting multiple client channels
4. ✅ Always explains actions before executing
5. ✅ Always confirms before messaging clients
6. ❌ Never deletes data without explicit confirmation
7. ❌ Never sends spam
8. ✅ Logs all approval requests

## Tools with Safety Features

### 1. Airtable Write Tool (`airtable_write.py`)
**Actions:**
- `create_record` - Single record (no approval)
- `update_record` - Single record (no approval)
- `delete_record` - Single record (shows warning)
- `bulk_create` - Multiple records (approval if >5)
- `bulk_update` - Multiple records (approval if >5)
- `bulk_delete` - Multiple records (approval if >3)

**Safety constants:**
```python
MAX_RECORDS_WITHOUT_APPROVAL = 5
MAX_BULK_DELETE_WITHOUT_APPROVAL = 3
```

### 2. Approval Request Tool (`request_approval.py`)
General-purpose approval system for any action requiring human oversight.

**Usage:**
```bash
python execution/tools/request_approval.py "bulk_update_clients" "Updating 50 client records with new status"
```

## Modifying Safety Limits

To adjust safety limits, edit the constants in `execution/tools/airtable_write.py`:

```python
# Increase limits (not recommended)
MAX_RECORDS_WITHOUT_APPROVAL = 10  # Currently: 5
MAX_BULK_DELETE_WITHOUT_APPROVAL = 5  # Currently: 3

# Decrease limits (more conservative)
MAX_RECORDS_WITHOUT_APPROVAL = 3  # Stricter
MAX_BULK_DELETE_WITHOUT_APPROVAL = 1  # Very strict
```

## Monitoring

All approval requests are logged to:
```
.tmp/logs/approval_requests.jsonl
```

Each log entry contains:
- Timestamp
- Action type
- Action details
- Status (pending_approval)

## Best Practices

1. **Review logs regularly** - Check `.tmp/logs/approval_requests.jsonl`
2. **Start conservative** - Begin with strict limits, relax if needed
3. **Test in dev first** - Test bulk operations before deploying
4. **Document exceptions** - If you approve unusual requests, document why
5. **Client education** - Inform clients about what the agent can/cannot do

## Future Enhancements

Potential improvements:
- Two-factor approval for deletions
- Scheduled operations with approval queue
- Rollback mechanism for bulk changes
- Approval via Slack or email
- Role-based permissions (admin vs. regular user)
- Dry-run mode (preview changes before applying)

## Emergency Procedures

If the agent makes unauthorized changes:

1. **Stop the agent immediately**
2. **Check logs**: `.tmp/logs/`
3. **Review approval_requests.jsonl** for what happened
4. **Restore from backups** (Airtable has revision history)
5. **Tighten limits** in tool configurations
6. **Update constraints** in client config

## Testing Safety Features

Test the approval system:

```bash
# This should require approval (>5 records)
python execution/tools/airtable_write.py bulk_create BASE_ID TABLE_NAME '[{...}, {...}, {...}, {...}, {...}, {...}]'

# This should work without approval (<=5 records)
python execution/tools/airtable_write.py bulk_create BASE_ID TABLE_NAME '[{...}, {...}]'
```

---

## Summary

✅ **Safe operations:** Read data, send individual messages, small updates
⚠️ **Requires approval:** Bulk operations, deletions, client-facing changes
❌ **Blocked:** No destructive operations without explicit confirmation

The agent is designed to be helpful but cautious. When in doubt, it asks for permission.
