# Client Deployment Checklist

Use this checklist before packaging and sending the agent to a client.

## Pre-Deployment Security Audit

### 1. Remove Sensitive Data
- [ ] Delete or sanitize `.env` file (replace with `.env.template`)
- [ ] Remove your personal API keys from all files
- [ ] Delete `credentials.json` and `token.json` (Google OAuth)
- [ ] Clear `.tmp/` directory and all logs
- [ ] Remove any client-specific data from test runs
- [ ] Check for hardcoded secrets in Python files

### 2. Clean Up Development Files
- [ ] Remove test scripts (`test_*.py`)
- [ ] Delete `.tmp/` contents
- [ ] Remove `__pycache__/` directories
- [ ] Delete `venv/` (client will create their own)
- [ ] Remove `.git/` if sharing via zip (keep if using Git repo)
- [ ] Delete any `.backup` files

### 3. Verify Installation Files
- [ ] `install.bat` works on Windows
- [ ] `install.sh` works on Mac/Linux
- [ ] `configure.bat` properly validates API keys
- [ ] `configure.sh` properly validates API keys
- [ ] Scripts handle errors gracefully
- [ ] All scripts have proper permissions (chmod +x for .sh files)

### 4. Documentation Review
- [ ] `CLIENT_INSTALL.md` is complete and accurate
- [ ] `CLIENT_PACKAGE_README.md` clearly explains what's included
- [ ] All instructions are non-technical enough for client
- [ ] API key instructions are step-by-step with links
- [ ] Troubleshooting section covers common issues
- [ ] Support contact info is correct

### 5. Test Installation (Clean Environment)
- [ ] Test `install.bat` on a fresh Windows machine
- [ ] Test `install.sh` on a fresh Mac/Linux machine
- [ ] Verify `configure.bat` creates valid `.env`
- [ ] Verify `configure.sh` creates valid `.env`
- [ ] Test agent starts successfully with `start_agent.bat/.sh`
- [ ] Test API endpoint at http://localhost:8000
- [ ] Verify all tools work with client's credentials

### 6. Client-Specific Configuration
- [ ] Update `config/clients/youtube_agency.json` with correct client name
- [ ] Customize system prompt if needed
- [ ] Add/remove tools based on client's subscription level
- [ ] Set appropriate constraints
- [ ] Configure output destinations (if applicable)

### 7. Cost & Usage Transparency
- [ ] Document estimated monthly API costs
- [ ] Explain what they're paying for
- [ ] Provide usage monitoring instructions
- [ ] Include Anthropic dashboard link for bill tracking

### 8. Legal & Compliance
- [ ] Include any required license files
- [ ] Add terms of service if applicable
- [ ] Include privacy policy or data handling statement
- [ ] Document data retention policies

## Packaging Instructions

### Option A: ZIP File (Simple)
```bash
# Clean the directory first
rm -rf .tmp venv __pycache__ .git

# Create client package
zip -r pm-agent-client-package.zip . \
  -x "*.pyc" \
  -x "*.backup" \
  -x ".env" \
  -x "credentials.json" \
  -x "token.json" \
  -x ".git/*"
```

### Option B: Git Repository (Preferred)
```bash
# Create a new clean branch for client
git checkout -b client-release

# Remove sensitive files
git rm --cached .env credentials.json token.json
git rm -r .tmp

# Commit clean version
git add .
git commit -m "Client release package"

# Push to private repo client can access
git push origin client-release
```

## What to Send the Client

1. **The Package:**
   - ZIP file or Git repo link
   - Name: `pm-agent-v1.0-client-package.zip`

2. **Getting Started Email:**
   ```
   Subject: Your PM Agent Installation Package

   Hi [Client Name],

   Attached is your PM Agent installation package. This will help you
   manage your YouTube production workflow directly from your computer.

   FIRST STEP: Open CLIENT_PACKAGE_README.md to get started.

   The installation takes about 15 minutes and requires:
   - Anthropic API key (I'll send setup instructions)
   - Your Slack workspace access
   - Your Airtable API key

   If you run into any issues, check CLIENT_INSTALL.md or reach out
   to me directly.

   Best,
   [Your Name]
   ```

3. **API Key Setup Email:**
   ```
   Subject: API Keys for Your PM Agent

   Hi [Client Name],

   Before installing, you'll need to create API keys. Here's what to do:

   1. ANTHROPIC (AI Engine) - $10-30/month
      - Go to: https://console.anthropic.com/
      - Sign up and add a payment method
      - Create an API key
      - Set a usage limit of $50/month to be safe

   2. SLACK (Free)
      - Go to: https://api.slack.com/apps
      - Create a new app (instructions in CLIENT_INSTALL.md)
      - You'll need workspace admin access

   3. AIRTABLE (Free for your current plan)
      - Go to: https://airtable.com/create/tokens
      - Create a personal access token
      - Grant access to your YouTube Projects base

   Once you have these, run the installer and follow the prompts.

   Let me know if you have questions!

   Best,
   [Your Name]
   ```

## Post-Deployment

### First Week Check-In
- [ ] Confirm client successfully installed agent
- [ ] Verify agent is working with their credentials
- [ ] Walk through 3-5 example queries
- [ ] Show them the logs directory for troubleshooting
- [ ] Explain how to restart if it crashes

### First Month Check-In
- [ ] Review API usage/costs with client
- [ ] Ask for feedback on agent capabilities
- [ ] Identify new tools they need
- [ ] Update system prompt based on usage patterns
- [ ] Check for any errors in logs

### Ongoing Maintenance
- [ ] Send updates via Git (if using repo) or new ZIP files
- [ ] Document changes in CHANGELOG.md
- [ ] Test updates in clean environment before sending
- [ ] Provide migration guide if breaking changes

## Emergency Contacts

If client reports issues, ask for:

1. **Operating System** (Windows/Mac/Linux version)
2. **Python Version** (`python --version`)
3. **Error Message** (exact text or screenshot)
4. **Log File** (`.tmp/logs/agent.log`)
5. **What They Were Doing** (what question they asked)

## Rollback Plan

If deployment fails:

1. Keep previous working version available
2. Document rollback steps in `ROLLBACK.md`
3. Test rollback procedure before deployment
4. Have client's credentials ready to reconfigure

---

## Final Verification

Before sending to client, run through this 5-minute test:

```bash
# 1. Clean install
rm -rf venv .tmp .env

# 2. Run installer
./install.sh  # or install.bat on Windows

# 3. Configure with TEST credentials
./configure.sh

# 4. Start agent
./start_agent.sh

# 5. Test basic queries
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'

# 6. Check logs
cat .tmp/logs/agent.log
```

If all tests pass: ✅ Ready to deploy!
