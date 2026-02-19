# Automations Guide

## Overview

The PM agent runs 7 automated workflows via `config/automations.json`, executed by `execution/scheduler.py` inside the FastAPI process.

## Automation List

| ID | Schedule | Purpose |
|----|----------|---------|
| `simon_daily_summary` | 09:30, 12:15, 15:00 Mon-Fri | Daily briefing DM to Simon |
| `simon_logoff_summary` | 17:30 Mon-Fri | End-of-day wrap-up with A-F rating |
| `client_followup_reminder` | 10:00, 14:00 Mon-Fri | Clients not responding to video reviews |
| `deadline_editor_alert` | 09:00 Mon-Fri | Videos with deadline tomorrow |
| `unanswered_client_alert` | Every 15min, 9:30-15:00 Mon-Fri | Client messages without reply after 30min |
| `unanswered_editor_alert` | Every 15min, 9:30-15:00 Mon-Fri | Editor questions not tended to after 30min |
| `payment_reminder` | 09:00 daily | Payment requests on 15th/30th only |

## How Automations Work

### Architecture
1. `config/automations.json` defines the automation, schedule, and step pipeline
2. `execution/scheduler.py` reads the config at startup and registers APScheduler jobs
3. Each automation runs its steps sequentially — output from earlier steps feeds into later ones
4. The `${steps.<step_id>.field}` syntax passes data between steps
5. The `${ENV_VAR}` syntax resolves environment variables at runtime

### Schedule Formats
- **Fixed times**: `{"times": ["09:30", "12:15"], "days": "mon-fri"}`
- **Interval**: `{"interval_minutes": 15, "start_hour": 9, "end_hour": 15, "days": "mon-fri"}`
  - Interval configs are expanded to explicit time arrays internally

### CLI Patterns
- `action_json`: `script.py <action> '<json_params>'` — most tools/ scripts
- `argparse`: `script.py --flag value` — some execution/ scripts
- `positional`: `script.py <action> <arg1> <arg2>` — slack_write.py

### Step Data Flow
Use `"input_steps"` to aggregate outputs from previous steps:
```json
{
  "params": {
    "input_steps": ["step1", "step2"],
    "recipient_name": "Simon"
  }
}
```
The scheduler collects outputs from named steps into an `input_data` dict.

## Monitoring & Troubleshooting

### Logs
All automation runs are logged to `.tmp/logs/automations.jsonl`. Each entry includes:
- Automation ID and trigger time
- Step-by-step execution results
- Success/failure status
- Duration

### Common Issues

**Automation not running:**
- Check `"enabled": true` in config
- Check scheduler startup logs for registration messages
- Verify timezone matches (`US/Eastern`)

**Step failure stops pipeline:**
- By design, a failing step halts the entire automation (line 235: `break`)
- The automation will retry at its next scheduled time
- Check `.tmp/logs/automations.jsonl` for the error

**Interval automations skipped:**
- If a run takes >15 minutes, the next run is skipped (concurrency guard)
- This is expected behavior to prevent overlapping runs

**LLM-heavy steps timing out:**
- `slack_task_scanner.py` scans all channels with LLM calls (~$0.15/run)
- Default subprocess timeout is 180s
- If you have many channels, consider raising the timeout in scheduler.py

### Cache Files
- `.tmp/status_cache.json` — Status change monitor (tracks Airtable statuses)
- `.tmp/notified_messages.json` — Response monitor (avoids duplicate alerts)
- First run after cache deletion re-caches without alerting (correct behavior)

## Adding a New Automation

1. Create the tool script in `execution/tools/` following the `action_json` pattern
2. Add an entry to `config/automations.json` with:
   - Unique `id`
   - `schedule` with times/interval and days
   - `steps` array with tool references and params
3. Register the tool in `config/clients/youtube_agency.json` `available_tools`
4. Restart the API server to pick up the new config

## Dashboard Endpoints

- `GET /api/automations` — List all automations with status
- `POST /api/automations/{id}/trigger` — Manually trigger an automation
- `GET /api/automations/{id}/history` — View recent run history
