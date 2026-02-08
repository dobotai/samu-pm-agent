# Editor Task Report - Directive

## Purpose
Generate a comprehensive per-editor task summary by cross-referencing Slack channel activity with Airtable video statuses. This gives a single source of truth: what editors are saying in Slack + where their videos actually stand in the pipeline.

## When to Run
- Daily or on-demand when PM needs a status overview
- Before team syncs or client updates
- When investigating delivery delays or editor performance

## Data Sources

### 1. Slack Editor Channels (Activity + Context)
Each editor has a dedicated Slack channel (`#<name>-editing`) where:
- Airtable bots post assignment/review/revision notifications
- Editors post check-ins, ETAs, and questions
- PMs (Simon, Samu) post review notes and client feedback
- Thread replies contain critical decision context

### 2. Airtable Videos Table (Pipeline Status)
The Videos table tracks the official status of every video:
- `41 - Sent to Editor` → Editor has been assigned
- `50 - Editor Confirmed` → Editor acknowledged, working on it
- `59 - Editing Revisions` → Reviewed, revisions needed
- `60 - Submitted for QC` → Editor submitted, awaiting internal review
- `75 - Sent to Client For Review` → Client is reviewing
- `80 - Approved By Client` → Client approved, ready for scheduling
- `100 - Scheduled - DONE` → Published/complete

## Automated Execution

```bash
# Full report, all editors, last 48 hours
python execution/editor_task_report.py

# Single editor
python execution/editor_task_report.py --editor megh

# Custom timeframe
python execution/editor_task_report.py --hours 24

# JSON output for programmatic use
python execution/editor_task_report.py --output json

# Only editors with active Airtable videos
python execution/editor_task_report.py --editors-only
```

The script handles all data fetching, cross-referencing, and formatting automatically.
Zero LLM cost - all analysis is deterministic pattern matching.

## Manual Process (Reference)

### Step 1: Read Slack Channels
```bash
# Read last 48 hours with thread replies for each editor channel
python execution/slack_read_channel.py "<CHANNEL_ID>" --since 48 --output json
```

**Editor Channel IDs:**
| Editor | Channel ID |
|--------|-----------|
| Rafael | C070VSRPP6H |
| Ananda | C071NUME7EC |
| Amna | C079U4HF8GM |
| Megh | C08HNVDCGQ4 |
| Suhaib | C08PCKQBTV5 |
| Sakib | C09LQKUC7E0 |
| Syed N | C09S6EXECQP |
| Chris | C09S8G1LKT6 |
| Jov | C0A0SFWPR3L |
| Sanjit | C0A13RZCLMT |
| Raj | C0A17EL29EZ |
| Lin | C0A1PCUQA7M |
| Ruben | C0A2PK6FWF3 |
| Seba | C0A3CPG5Z3Q |
| Golden | C0A3D58KYT1 |
| Kyrylo | C0A5H3PKA3E |
| Rafiu | C0A5HJGF7EX |
| Shafen | C0A7UAZ22DN |
| Ghayas | C0A7Z3F8K8T |
| Jaydi | C0ABFUHSWN9 |
| Alaa | C0ACDK8D248 |
| Denis | C0ACR0N0R98 |
| Anuj | C0A73RECBQS |

### Step 2: Pull Airtable Video Statuses
```bash
# Pull all videos in active editing stages
python execution/airtable_read.py "Videos" \
  --fields "Video ID,Client,Video Number,Format,Editing Status,Assigned Editor" \
  --filter "OR({Editing Status}='41 - Sent to Editor',{Editing Status}='50 - Editor Confirmed',{Editing Status}='59 - Editing Revisions',{Editing Status}='60 - Submitted for QC',{Editing Status}='75 - Sent to Client For Review',{Editing Status}='80 - Approved By Client')" \
  --output json
```

Then resolve Client and Editor names by pulling:
```bash
python execution/airtable_read.py "Clients" --fields "Name" --output json
python execution/airtable_read.py "Team" --fields "Name" --output json
```

### Step 3: Cross-Reference and Generate Report

For each editor channel, produce a summary in this format:

```
### #<editor>-editing (<Editor Name>)

**Airtable Pipeline:** <count> active videos
| Video | Status |
|-------|--------|
| Client Video #X | <Airtable status> |

**1. <Video Name> - <Task Description>** `<PRIORITY>`
- <Slack context: what's happening, ETAs, blockers>
- **Airtable:** <status from pipeline>

**Bottom line:** <1-sentence summary of editor's state>
```

## Report Rules

### Priority Labels
- `HIGH` - Urgent, blocking, or client-escalated
- `MEDIUM` - Active work, standard timeline
- `LOW` - Informational, future planning
- `DONE` - Completed in this period

### Context Attribution
**CRITICAL:** Messages immediately following Airtable bot notifications are contextually about that notification. For example:
- Airtable: "DanVid10 Shorts reviewed with revisions"
- Samu: "the shorts are really echo-y"
- This echo complaint is about DanVid10 Shorts, NOT whatever was discussed before.

### Thread Context
Always include thread replies - they contain decisions, escalations, and task resolutions that top-level messages miss. Format:
```
[timestamp] User: message
  -> [timestamp] Reply User: reply text
```

### Airtable Status Cross-Reference
Every video mentioned in Slack MUST include its current Airtable status. Flag discrepancies:
- If Slack says "submitted" but Airtable says "50 - Editor Confirmed" → status not updated
- If Airtable says "80 - Approved By Client" but Slack still discussing revisions → stale Slack context
- If editor hasn't responded to check-ins but has active videos → needs follow-up

### No Activity Flag
If an editor has active Airtable videos but zero Slack messages in 48h, flag as: "No check-ins or updates. Needs follow-up."

## Self-Annealing Notes
- `conversations_list` doesn't paginate fully for private channels. Use channel IDs directly (table above).
- Unicode characters (like arrows) can fail on Windows. Use ASCII alternatives (`->` instead of `↳`).
- Slack rate limit for `conversations.replies` is ~50 req/min. The `max_threads=50` cap per channel handles this.
- Thread replies are fetched only for messages with `reply_count > 0` to minimize API calls.
