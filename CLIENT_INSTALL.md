# Client Installation Guide
## YouTube Agency Project Management Agent

### What This Does
This agent helps you manage your YouTube projects by connecting to your Slack workspace, Airtable database, and Google Drive. You can ask it questions in plain English like:
- "What videos are due this week?"
- "Show me messages I haven't responded to"
- "What's the status of Taylor's videos?"

---

## Installation Steps

### Step 1: Get Your API Keys

You'll need to create accounts and get API keys from these services:

#### 1.1 Anthropic API Key (Required - $20/month budget recommended)
1. Go to https://console.anthropic.com/
2. Create an account or sign in
3. Go to "API Keys" in settings
4. Click "Create Key"
5. Copy the key (starts with `sk-ant-api03-...`)
6. **Keep this safe!** You'll need it in Step 3

#### 1.2 Slack Bot Token (Required)
1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name it "PM Agent" and select your workspace
4. Go to "OAuth & Permissions" in the sidebar
5. Under "Scopes" → "Bot Token Scopes", add these:
   - `channels:read`
   - `channels:history`
   - `users:read`
   - `chat:write`
   - `reactions:write`
6. Click "Install to Workspace" at the top
7. Copy the "Bot User OAuth Token" (starts with `xoxb-...`)

#### 1.3 Airtable API Key (Required)
1. Go to https://airtable.com/create/tokens
2. Click "Create new token"
3. Give it a name like "PM Agent"
4. Under "Scopes", select:
   - `data.records:read`
   - `data.records:write`
   - `schema.bases:read`
5. Under "Access", choose your base (YouTube Projects)
6. Click "Create token"
7. Copy the token (starts with `pat...`)

#### 1.4 Airtable Base ID (Required)
1. Go to your Airtable base in a web browser
2. Look at the URL: `https://airtable.com/appXXXXXXXXXXXXXX/...`
3. Copy the part that starts with `app` (e.g., `apph2RxHbsyqmCwxk`)

#### 1.5 Google Drive (Optional - for Drive file access)
If you need the agent to access Google Drive files:
1. Ask your IT admin or follow Google's service account guide
2. This is advanced - skip for now if unsure

---

### Step 2: Install the Agent

#### Windows:
1. Double-click `install.bat`
2. Follow the on-screen prompts
3. The installer will:
   - Check if Python is installed (and install it if needed)
   - Create a safe environment for the agent
   - Install required software packages

#### Mac/Linux:
1. Open Terminal
2. Navigate to this folder: `cd /path/to/agent`
3. Run: `bash install.sh`
4. Follow the on-screen prompts

---

### Step 3: Configure Your API Keys

After installation completes:

1. Double-click `configure.bat` (Windows) or run `bash configure.sh` (Mac/Linux)
2. You'll be asked to enter each API key
3. The wizard will:
   - Validate each key works
   - Save them securely in a hidden `.env` file
   - Test the connection to each service

**What gets entered:**
```
Anthropic API Key: sk-ant-api03-[your key]
Slack Bot Token: xoxb-[your token]
Airtable API Key: pat[your token]
Airtable Base ID: app[your base id]
```

---

### Step 4: Start the Agent

#### Windows:
- Double-click `Start PM Agent.bat` on your desktop
- A window will open showing the agent is ready
- Open your web browser to: http://localhost:8000

#### Mac/Linux:
- Double-click `Start PM Agent` on your desktop
- Or run: `bash start_agent.sh`
- Open your web browser to: http://localhost:8000

---

## Using the Agent

Once started, you can:

### Web Interface (Recommended)
1. Go to http://localhost:8000 in your browser
2. Type your questions in plain English
3. Examples:
   - "What tasks are urgent today?"
   - "Show me Taylor's videos"
   - "Have any clients sent messages I haven't responded to?"
   - "What's the status of all projects?"

### Command Line Interface
If you prefer terminal:
```bash
# Windows
agent-chat.bat

# Mac/Linux
./agent-chat.sh
```

---

## Troubleshooting

### "Python not found"
- The installer should handle this, but if not:
- Download Python from https://python.org (version 3.10 or newer)
- During install, check "Add Python to PATH"
- Restart your computer
- Run the installer again

### "Invalid API Key"
- Go back to the service's website
- Regenerate the API key
- Run `configure.bat` again with the new key

### "Can't connect to Slack/Airtable"
- Check your internet connection
- Verify the API key has the correct permissions
- Make sure you installed the Slack app to your workspace

### "Agent won't start"
1. Open `logs/agent.log` in this folder
2. Look for error messages
3. Contact support with the error message

---

## Security Notes

- Your API keys are stored in `.env` (hidden file in this folder)
- **Never share this file** - it contains your credentials
- The agent runs locally on your computer - nothing is sent to external servers except:
  - API calls to Anthropic (to power the AI)
  - API calls to Slack/Airtable (to read your data)
- You can inspect all code in the `execution/` folder

---

## Updating the Agent

When new versions are released:

1. Download the new version
2. Copy your `.env` file from the old installation to the new folder
3. Run `install.bat` in the new folder
4. Start the agent as usual

**Or:** If you're comfortable with Git:
```bash
git pull origin main
pip install -r requirements.txt --upgrade
```

---

## Support

For questions or issues:
- Check the troubleshooting section above
- Email: [your support email]
- Documentation: See `CLAUDE.md` for technical details

---

## What's Running?

When you start the agent, these processes run:

1. **API Server** (`execution/api_server.py`)
   - Listens on http://localhost:8000
   - Handles your questions
   - Routes requests to the orchestrator

2. **Orchestrator** (`execution/orchestrator.py`)
   - The "brain" of the agent
   - Decides which tools to use
   - Calls Slack/Airtable/Drive APIs as needed

3. **Execution Tools** (in `execution/tools/`)
   - Individual scripts that do specific tasks
   - Read Slack, write to Airtable, etc.

You can safely close the terminal/window to stop the agent.

---

## Cost Estimate

Monthly costs you'll pay directly to services:

- **Anthropic API**: ~$10-30/month (depends on usage)
  - Each question costs about $0.01-0.10
  - 100-300 questions per month = ~$20
- **Slack**: Free (if using free Slack plan)
- **Airtable**: Free for small teams, $20/month for Pro
- **Google Drive**: Included with Google Workspace

**Total: $10-50/month** depending on usage.

---

## Uninstalling

To remove the agent:

1. Stop the agent (close the window)
2. Delete this entire folder
3. (Optional) Revoke API keys from Anthropic/Slack/Airtable dashboards
4. (Optional) Uninstall Python if you don't use it for anything else

---

## Privacy & Data

- All data stays on your computer
- API calls go directly from your computer to Slack/Airtable/Anthropic
- Logs are saved in `.tmp/logs/` (you can delete these anytime)
- No telemetry or tracking
- No data is sent to the agent developer
