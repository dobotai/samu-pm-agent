# PM Agent - Client Installation Package

## What's Included

This package contains everything needed to install and run your PM Agent locally on your computer.

### Files Overview

**Installation Files:**
- `install.bat` - Windows installer
- `install.sh` - Mac/Linux installer
- `configure.bat` - Windows configuration wizard
- `configure.sh` - Mac/Linux configuration wizard
- `start_agent.bat` / `start_agent.sh` - Starts the agent
- `agent_chat.bat` / `agent_chat.sh` - Terminal chat interface

**Documentation:**
- `CLIENT_INSTALL.md` - **START HERE** - Complete installation guide
- `README.md` - Technical overview (optional reading)
- `.env.template` - Reference for API keys (don't edit directly)

**Core Agent Files:**
- `execution/` - Agent tools and scripts
- `config/` - Configuration files
- `requirements.txt` - Python dependencies
- Various other support files

## Quick Start

### For Windows Users:
1. Read `CLIENT_INSTALL.md` to get your API keys
2. Double-click `install.bat`
3. Follow the prompts
4. Double-click `configure.bat` to enter your API keys
5. Double-click `Start PM Agent.bat` on your desktop
6. Open browser to http://localhost:8000

### For Mac/Linux Users:
1. Read `CLIENT_INSTALL.md` to get your API keys
2. Open Terminal and navigate to this folder
3. Run: `bash install.sh`
4. Run: `bash configure.sh` to enter your API keys
5. Run: `./start_agent.sh`
6. Open browser to http://localhost:8000

## What You'll Need

Before installing, gather these API keys (see `CLIENT_INSTALL.md` for detailed instructions):

1. **Anthropic API Key** - Powers the AI ($10-30/month)
   - Get from: https://console.anthropic.com/

2. **Slack Bot Token** - Reads your Slack workspace (free)
   - Get from: https://api.slack.com/apps

3. **Airtable API Key** - Accesses your project database (free to $20/month)
   - Get from: https://airtable.com/create/tokens

4. **Airtable Base ID** - Found in your Airtable URL
   - Example: `apph2RxHbsyqmCwxk`

## System Requirements

- **Operating System:** Windows 10/11, macOS 10.14+, or modern Linux
- **Python:** 3.10 or newer (installer will check)
- **RAM:** 2GB minimum, 4GB recommended
- **Disk Space:** 500MB for installation
- **Internet:** Required for API calls

## Security & Privacy

- All data stays on your computer
- API calls go directly to Anthropic/Slack/Airtable
- Your credentials are stored in a hidden `.env` file
- No telemetry or tracking
- No data sent to agent developer

## Support

Questions? Issues?

1. Check `CLIENT_INSTALL.md` troubleshooting section
2. Review the logs in `.tmp/logs/`
3. Contact your agent provider

## What This Agent Does

The PM Agent helps manage your YouTube production workflow by:

- Reading project status from Airtable
- Monitoring Slack for team communication
- Answering questions in plain English
- Identifying bottlenecks and delays
- Generating status reports

**Example questions you can ask:**
- "What videos are due this week?"
- "Show me all blocked tasks"
- "Has Taylor responded to my message?"
- "What's the status of Nicolas Video #36?"
- "Give me an end-of-day checklist"

## Monthly Cost Estimate

- **Anthropic API**: $10-30 (based on usage)
- **Slack**: Free
- **Airtable**: Free to $20 (depends on plan)
- **Total**: $10-50/month

## Updating the Agent

When updates are available:

1. Download the new package
2. Copy your `.env` file from the old installation
3. Run `install.bat` or `install.sh` in the new folder
4. Start the agent as usual

## Uninstalling

To remove:

1. Stop the agent (close the window)
2. Delete the installation folder
3. (Optional) Revoke API keys from service dashboards
4. (Optional) Uninstall Python if not used elsewhere

---

**Need help getting started?** Open `CLIENT_INSTALL.md` for step-by-step instructions with screenshots.
