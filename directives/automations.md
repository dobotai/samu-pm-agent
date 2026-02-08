# Automation System

## Overview
The automation system runs scheduled tasks inside the FastAPI server process using APScheduler. It replaces external cron daemons and works in Railway's single-process model.

- Config: `config/automations.json`
- Engine: `execution/scheduler.py`
- Dashboard: `static/dashboard.html` (served at `/`)
- Logs: `.tmp/logs/automations.jsonl`

## Architecture

```
FastAPI (api_server.py)
  ├── on_startup → AutomationScheduler.start()
  ├── GET  /api/automations           → list all + status
  ├── GET  /api/automations/{id}/history → run log
  ├── POST /api/automations/{id}/trigger → manual run
  ├── POST /api/automations/{id}/toggle  → enable/disable
  └── on_shutdown → AutomationScheduler.shutdown()
```

Each automation runs its steps sequentially. A step calls a tool script via subprocess. If any step fails, subsequent steps are skipped and the run is logged as failed.

## Active Automations

### Simon Daily Summary
- **Schedule:** 9:30 AM, 12:15 PM, 3:00 PM EST (Mon-Fri)
- **Steps:**
  1. `slack_task_scanner.py extract_tasks` — LLM scan for tasks (~$0.15)
  2. `slack_read_channel.py #project-manager` — Recent PM channel messages
  3. `pm_analytics.py get_attention_needed` — Urgent items
  4. `pm_analytics.py get_unfollowed_messages` — Unanswered messages
  5. `summary_generator.py generate` — Claude produces Slack-formatted summary (~$0.02-0.05)
  6. `slack_write.py send_dm` — DM to Simon
- **Cost per run:** ~$0.17-0.20
- **Daily cost (3 runs):** ~$0.50-0.60

## How to Add a New Automation

### Step 1: Define in config/automations.json

```json
{
  "id": "my_automation",
  "name": "My Automation",
  "description": "What it does",
  "enabled": true,
  "schedule": { "times": ["09:00", "17:00"], "days": "mon-fri" },
  "steps": [
    {
      "id": "step_one",
      "tool": "execution/tools/some_tool.py",
      "cli_pattern": "action_json",
      "action": "some_action",
      "params": {"key": "value"},
      "description": "What this step does"
    }
  ]
}
```

### Step 2: Choose the CLI pattern

| Pattern | Format | Used by |
|---------|--------|---------|
| `action_json` | `script.py <action> '<json>'` | pm_analytics, slack_task_scanner, summary_generator |
| `argparse` | `script.py <positional> --flag val` | slack_read_channel |
| `positional` | `script.py <action> <arg1> <arg2>` | slack_write |

### Step 3: Use variable substitution

- `${ENV_VAR}` — Environment variable
- `${steps.<step_id>.field}` — Output field from a previous step

### Step 4: Test manually

Trigger via the dashboard "Run Now" button or the API:
```
POST /api/automations/my_automation/trigger
```

### Step 5: Deploy

Push to git. Railway auto-deploys. Scheduler starts on server boot.

## Schedule Format

- `times`: Array of `"HH:MM"` strings (24h format, in configured timezone)
- `days`: `"mon-fri"`, `"*"` (every day), or `"mon,wed,fri"`

## Monitoring

- **Dashboard:** `https://your-app.railway.app/`
- **Logs:** `.tmp/logs/automations.jsonl` (one JSON line per run)
- **API:** `GET /api/automations` returns all statuses as JSON
- **Health check:** `GET /health` includes `scheduler_running` field

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Scheduler not starting | Check `config/automations.json` is valid JSON |
| Step fails with "Tool not found" | Verify the `tool` path is relative to project root |
| Wrong time zone | Set `timezone` in automations.json (default: US/Eastern) |
| Summary too generic | Add more channels to the gather steps |
| DM not sending | Verify `SIMON_SLACK_USER_ID` in .env, check bot has `chat:write` scope |
| Railway restart loses state | Expected — in-memory state resets, but log file persists. Schedule recalculates on boot. |

## Self-Annealing Notes
<!-- Add learnings as you discover them -->
