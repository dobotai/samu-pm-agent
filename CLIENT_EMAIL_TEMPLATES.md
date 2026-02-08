# Client Communication Templates

Use these email templates when deploying the agent to your client.

---

## Email 1: Initial Package Delivery

**Subject:** Your PM Agent Installation Package is Ready

**Body:**
```
Hi [Client Name],

Your custom PM Agent is ready for installation! This agent will help you manage your YouTube production workflow by connecting to your Slack, Airtable, and Google Drive.

WHAT IT DOES:
- Answers questions about project status in plain English
- Monitors Slack for unanswered messages
- Tracks video deadlines and bottlenecks
- Generates daily reports and checklists
- Identifies what needs your attention

WHAT YOU'LL NEED:
Before installing, you'll need to create API keys (I'll send separate instructions):
- Anthropic API key (~$10-30/month for AI)
- Slack bot token (free)
- Airtable API key (free for your plan)

INSTALLATION TIME: About 15 minutes

GETTING STARTED:
1. Download the attached package
2. Extract it to a folder on your computer
3. Open "START_HERE.txt" for quick instructions
4. Read "CLIENT_INSTALL.md" for step-by-step setup

The installation wizard will guide you through everything. If you run into any issues, just reply to this email or call me at [your number].

Looking forward to seeing how this helps streamline your workflow!

Best,
[Your Name]

---

P.S. Everything runs locally on your computer - your data stays private and under your control.
```

---

## Email 2: API Keys Setup Guide

**Subject:** API Keys Setup for Your PM Agent

**Body:**
```
Hi [Client Name],

Before installing your PM Agent, you'll need to set up API keys from these services. This should take about 10 minutes.

═══════════════════════════════════════════════

1. ANTHROPIC (Powers the AI - Required)

Cost: $10-30/month based on usage

Steps:
1. Go to: https://console.anthropic.com/
2. Create an account (use your business email)
3. Click "Get API Keys" or go to Settings → API Keys
4. Click "Create Key"
5. Name it "PM Agent"
6. Copy the key (starts with sk-ant-api03-...)
7. IMPORTANT: Set a usage limit of $50/month to prevent surprises
   - Go to Settings → Limits
   - Set Monthly Limit: $50

Save this key - you'll need it during installation.

═══════════════════════════════════════════════

2. SLACK (Connects to Your Workspace - Required)

Cost: Free

Steps:
1. Go to: https://api.slack.com/apps
2. Click "Create New App"
3. Choose "From scratch"
4. Name: "PM Agent"
5. Select your workspace
6. In the sidebar, go to "OAuth & Permissions"
7. Scroll to "Scopes" → "Bot Token Scopes"
8. Add these scopes:
   - channels:read
   - channels:history
   - users:read
   - chat:write
   - reactions:write
9. Scroll to top and click "Install to Workspace"
10. Click "Allow"
11. Copy the "Bot User OAuth Token" (starts with xoxb-...)

Save this token - you'll need it during installation.

═══════════════════════════════════════════════

3. AIRTABLE (Accesses Project Database - Required)

Cost: Free for your current plan

Steps:
1. Go to: https://airtable.com/create/tokens
2. Click "Create new token"
3. Name: "PM Agent"
4. Under "Scopes", select:
   - data.records:read
   - data.records:write
   - schema.bases:read
5. Under "Access", choose your "YouTube Projects" base
6. Click "Create token"
7. Copy the token (starts with pat...)

Save this token - you'll need it during installation.

═══════════════════════════════════════════════

4. AIRTABLE BASE ID (Required)

Steps:
1. Go to your Airtable base in a web browser
2. Look at the URL: https://airtable.com/appXXXXXXXXXXXXXX/...
3. Copy the part that starts with "app" (e.g., app12345abcde)

Save this ID - you'll need it during installation.

═══════════════════════════════════════════════

SECURITY NOTES:
- Treat these keys like passwords - never share them
- The agent stores them locally in an encrypted format
- You can revoke any key at any time from the service's dashboard

Once you have all four items, run the installer and it will walk you through entering them.

Questions? Just reply to this email!

Best,
[Your Name]
```

---

## Email 3: Follow-Up After Installation

**Subject:** How's Your PM Agent Working?

**Body:**
```
Hi [Client Name],

Just checking in - did you get the PM Agent installed successfully?

QUICK TEST:
Once it's running, try asking these questions:
- "What videos are due this week?"
- "Show me urgent tasks"
- "What's Taylor's latest video status?"
- "Give me an end-of-day checklist"

COMMON ISSUES:
- If it says "API key invalid", double-check you copied the full key
- If Slack won't connect, make sure you installed the bot to your workspace
- If you see Python errors, try running install.bat again

USAGE TIPS:
- Start the agent each morning (or leave it running)
- Access it at http://localhost:8000 in your browser
- Ask questions in natural language - it's smart!
- Check the logs in .tmp/logs/ if something seems off

Need help? Give me a call at [your number] and we can screen-share to troubleshoot.

Looking forward to hearing how it's helping your workflow!

Best,
[Your Name]
```

---

## Email 4: One Month Check-In

**Subject:** PM Agent Check-In - New Features Available

**Body:**
```
Hi [Client Name],

It's been about a month since you installed the PM Agent. How's it working out?

USAGE REVIEW:
- Check your Anthropic dashboard to see your API costs: https://console.anthropic.com/
- Average cost should be $10-30/month depending on usage
- If it's higher, let me know and we can optimize

FEEDBACK REQUESTED:
I'd love to hear:
1. What features do you use most?
2. What questions do you wish it could answer?
3. Any issues or confusion?
4. Ideas for new capabilities?

NEW CAPABILITIES I CAN ADD:
Based on your workflow, I can build:
- Custom report formats
- Integration with other tools (Notion, Asana, etc.)
- Automated alerts for specific scenarios
- Team performance analytics
- Client sentiment tracking

Let me know what would be most valuable and I can add it to your agent.

Also, there's a new version available with bug fixes and performance improvements. Reply "update" if you'd like me to send it.

Thanks for using the agent!

Best,
[Your Name]
```

---

## Email 5: Emergency Support Response

**Subject:** Re: PM Agent Issue - Troubleshooting Steps

**Body:**
```
Hi [Client Name],

Sorry you're having trouble! Let's get this sorted out.

QUICK DIAGNOSTICS:
Can you help me understand what's happening?

1. What were you doing when the error occurred?
   (e.g., "I asked 'What tasks are due?' and it crashed")

2. What's the exact error message?
   (Send a screenshot if easier)

3. Check the log file:
   - Go to your PM Agent folder
   - Open .tmp/logs/agent.log
   - Scroll to the bottom
   - Copy/paste the last 20 lines

4. What's your setup?
   - Operating System: Windows/Mac/Linux?
   - Python version: Run "python --version" and tell me the result

IMMEDIATE FIXES TO TRY:

Option 1: Restart the Agent
- Close the agent window
- Run start_agent.bat (or .sh) again

Option 2: Reconfigure API Keys
- Run configure.bat (or .sh)
- Re-enter your API keys

Option 3: Reinstall
- Download the package again
- Copy your .env file from the old installation
- Run install.bat (or .sh)

If none of these work, let's schedule a quick screen-share call and I'll fix it directly.

Available times:
- [Day/Time option 1]
- [Day/Time option 2]
- [Day/Time option 3]

Or call me anytime at [your number].

Best,
[Your Name]
```

---

## Email 6: Update Available

**Subject:** PM Agent Update v1.1 Available

**Body:**
```
Hi [Client Name],

There's a new version of your PM Agent with improvements:

WHAT'S NEW IN v1.1:
- [List specific features/fixes]
- Faster response times
- Better error handling
- [Any new tools or capabilities]

UPDATING IS OPTIONAL
Your current version still works fine. Update only if you want the new features.

HOW TO UPDATE:

Easy Method:
1. Download the attached package
2. Extract it to a new folder
3. Copy your .env file from the old installation to the new folder
4. Run start_agent.bat (or .sh) from the new folder
5. Delete the old folder when you confirm it works

Your API keys will transfer automatically - no need to reconfigure.

Total time: 5 minutes

Git Method (if you're comfortable with Git):
1. cd to your agent folder
2. git pull origin main
3. pip install -r requirements.txt --upgrade

Questions? Just reply!

Best,
[Your Name]
```

---

## Phone/Video Call Script

When doing a screen-share to help the client:

**Opening:**
"Thanks for jumping on the call! Let me help you get this sorted out. Can you share your screen? I'll walk you through it step by step."

**Troubleshooting Flow:**
1. "First, let's check if Python is installed correctly. Open a command prompt/terminal and type: python --version"
2. "Now let's navigate to your PM Agent folder. Where did you extract it?"
3. "Let's run the installer. Double-click install.bat [or .sh]"
4. [Watch for errors and diagnose]
5. "Now let's configure your API keys. Run configure.bat [or .sh]"
6. "Do you have your Anthropic API key handy? Great, paste it when prompted."
7. [Continue through each key]
8. "Perfect! Now let's start the agent. Run start_agent.bat [or .sh]"
9. "Open your browser to localhost:8000"
10. "Try asking: 'What videos are due this week?'"

**Closing:**
"Great! Everything's working. Remember, you can always reach me if you run into issues. The agent will save your conversation history, so you can review past questions anytime."

---

## Slack/Text Message Templates

**Quick Check-In:**
```
Hey [Client]! How's the PM agent working out? Any issues or questions?
```

**Usage Reminder:**
```
FYI - Your PM agent can now [new feature]. Try asking it "[example question]"
```

**Cost Alert:**
```
Heads up - noticed your Anthropic API usage is higher than expected this month ($XX). Want me to take a look and optimize?
```

---

## Auto-Response for Support Email

**Out of Office / Initial Response:**
```
Thanks for reaching out about your PM Agent!

For immediate help:
1. Check CLIENT_INSTALL.md in your installation folder
2. Review logs in .tmp/logs/agent.log
3. Try restarting: run start_agent.bat or start_agent.sh

I'll respond to your specific issue within [X hours/by end of day].

For urgent issues, call [your number].

- [Your Name]
```
