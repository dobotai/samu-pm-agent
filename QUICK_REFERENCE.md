# PM Agent Quick Reference Card

**Print this page and keep it handy!**

---

## Starting the Agent

### Windows:
- Double-click **"Start PM Agent.bat"** on your desktop
- Wait for "Server running on http://localhost:8000"
- Open browser to: **http://localhost:8000**

### Mac/Linux:
- Run: `./start_agent.sh`
- Open browser to: **http://localhost:8000**

---

## Example Questions to Ask

### Project Status:
- "What videos are due this week?"
- "Show me Taylor's current videos"
- "What's the status of Nicolas Video #36?"
- "Which projects are delayed?"

### Team Management:
- "Who's working on what today?"
- "Show me tasks assigned to Sarah"
- "Which editors have urgent tasks?"

### Communication:
- "Have any clients sent messages I haven't responded to?"
- "Show me unanswered questions from Slack"
- "What messages need my attention?"

### Reports & Checklists:
- "Give me an end-of-day checklist"
- "Generate a client status report"
- "What tasks are urgent today?"
- "Show me QC items that need review"

### Cross-Checks:
- "Are Slack and Airtable in sync?"
- "Find status discrepancies between Slack and Airtable"
- "Who hasn't communicated recently?"

---

## Common Issues & Fixes

### Agent Won't Start
**Error:** "Port already in use"
**Fix:** Close the previous instance or restart your computer

### Can't Connect to Browser
**Check:** Is the agent running? Look for "Server running on..."
**Try:** http://127.0.0.1:8000 instead of localhost:8000

### "Invalid API Key" Error
**Fix:** Run `configure.bat` or `configure.sh` and re-enter your keys

### Slow Responses
**Cause:** Complex question or API delay (normal)
**Wait:** 5-15 seconds for most queries, 30-60s for complex reports

### Python Not Found
**Fix:** Install Python from https://python.org
**Important:** Check "Add Python to PATH" during installation

---

## File Locations

| Item | Location |
|------|----------|
| Agent Folder | Where you extracted the files |
| Configuration | `.env` (hidden file in agent folder) |
| Logs | `.tmp/logs/agent.log` |
| Session History | `.tmp/sessions/` |
| Config | `config/clients/youtube_agency.json` |

---

## Monthly Costs

| Service | Cost |
|---------|------|
| Anthropic API (AI) | $10-30/month |
| Slack | Free |
| Airtable | $0-20/month (your plan) |
| **Total** | **$10-50/month** |

Check usage: https://console.anthropic.com/

---

## Stopping the Agent

- Close the terminal/command window
- OR press `Ctrl+C` in the terminal

The agent will stop immediately. Your conversation history is saved.

---

## Getting Help

1. **Check the logs:**
   - Open `.tmp/logs/agent.log`
   - Look at the bottom for error messages

2. **Reconfigure:**
   - Run `configure.bat` or `configure.sh`
   - Re-enter your API keys

3. **Reinstall:**
   - Run `install.bat` or `install.sh` again
   - Copy your `.env` file first (to save keys)

4. **Contact Support:**
   - Email: [your support email]
   - Phone: [your support number]
   - Include: error message and what you were doing

---

## Security Reminders

- ✅ Keep `.env` file private (never share)
- ✅ Agent runs locally (your data stays on your computer)
- ✅ Revoke API keys if compromised
- ✅ Set usage limits on Anthropic dashboard ($50/month recommended)
- ❌ Don't commit `.env` to version control
- ❌ Don't share API keys in Slack/email

---

## Tips for Best Results

### Ask Specific Questions:
- **Good:** "What's the status of Taylor Video #11?"
- **Bad:** "Videos?"

### Use Full Names:
- **Good:** "Show me Taylor's videos"
- **Bad:** "Show me T's videos"

### Be Conversational:
- **Good:** "Which tasks are delayed and who should I follow up with?"
- **Bad:** "tasks delayed"

### Follow-Up Questions:
The agent remembers context:
- "Show me Taylor's videos"
- "Which ones are due this week?"
- "What's blocking the urgent one?"

---

## Advanced Usage

### Command Line Interface:
```bash
# Windows
agent_chat.bat

# Mac/Linux
./agent_chat.sh
```

### Check Agent Health:
Open browser to: http://localhost:8000/health

### View Available Tools:
Open browser to: http://localhost:8000/api/tools

### Clear Conversation History:
Delete files in `.tmp/sessions/`

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+C` | Stop agent |
| `Ctrl+R` | Reload browser page |
| `Ctrl+Shift+I` | Open browser dev tools (advanced) |

---

## Update Checklist

When new version arrives:

1. Stop the agent
2. Copy your `.env` file
3. Extract new package
4. Paste `.env` into new folder
5. Run `start_agent.bat/.sh`

No reconfiguration needed!

---

**Keep this reference card handy for quick lookups!**

For detailed help, see [CLIENT_INSTALL.md](CLIENT_INSTALL.md)
