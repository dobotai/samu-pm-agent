# Quick Start Guide - Railway Deployment

## ✅ Changes Made

**Authentication is now automatic!** No need to enter API keys in the web dashboard.

All authentication happens via Railway environment variables - much more secure and convenient.

---

## 🚀 Railway Setup (5 Minutes)

### Step 1: Set Environment Variables in Railway

Go to your Railway project → Click your service → **Variables** tab

Add these **4 required variables**:

```bash
ANTHROPIC_API_KEY=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

CLIENT_NAME=youtube_agency

SLACK_USER_TOKEN=xoxp-7040200606225-10264368545171-10267834473267-7e7db1dfbecc9d166dea1ae50bc1e3a4

CLIENT_API_KEY=production_secure_key_2024
```

**Optional variables** (if using these features):
```bash
AIRTABLE_API_KEY=your_airtable_key
GOOGLE_CREDENTIALS_JSON=base64_encoded_credentials
```

### Step 2: Wait for Auto-Deploy

Railway will automatically:
- ✅ Detect the new commit
- ✅ Rebuild the application
- ✅ Deploy with new authentication logic
- ⏱️ Takes 2-3 minutes

### Step 3: Generate Domain (if not done)

1. Go to **Settings** tab
2. Scroll to **Networking**
3. Click **"Generate Domain"**
4. Copy your URL: `https://samu-pm-agent-production.up.railway.app`

### Step 4: Access Your Dashboard

1. Open your Railway URL
2. **That's it!** No API key needed
3. Start asking questions immediately

---

## 🎯 Test Your Deployment

### 1. Health Check
Open: `https://your-app.railway.app/health`

Should return:
```json
{
  "status": "healthy",
  "service": "agent-api",
  "version": "1.0.0"
}
```

### 2. Dashboard
Open: `https://your-app.railway.app/`

Should show the PM Dashboard immediately ready to use.

### 3. Try a Query
Click on a Quick Action or type:
- "Which editors are active today?"
- "Summarize the Taylor client channel"

---

## 🔒 Security Improvements

**Before:** Users had to enter API key in browser (stored in localStorage)
- ❌ API key visible in browser
- ❌ Could be stolen from client side
- ❌ Manual entry required

**Now:** Authentication via Railway environment variables
- ✅ API keys never leave the server
- ✅ More secure (server-side only)
- ✅ Zero configuration for users
- ✅ Automatic authentication

---

## 📊 What Changed?

### 1. API Server (`execution/api_server.py`)
- Made API key header optional
- Authentication skipped when no key provided
- Uses `CLIENT_NAME` from environment variables

### 2. Dashboard JavaScript (`static/js/app.js`)
- Removed API key storage
- Removed API key validation
- Removed `X-API-Key` header from requests

### 3. Dashboard HTML (`static/index.html`)
- Removed API key input field
- Added security notice about server-side auth

---

## 🎉 Usage

Just open your Railway URL and start chatting!

**Example Queries:**
- "Which editors have been active today?"
- "Show me recent activity in Suhaib's channel"
- "What clients need immediate attention?"
- "Summarize the Taylor client project"
- "List all editing channels"

---

## 🔧 Troubleshooting

### Issue: "Invalid API key" error
**Cause:** Railway environment variables not set correctly

**Fix:**
1. Go to Railway → Variables tab
2. Verify `ANTHROPIC_API_KEY` is set
3. Verify `SLACK_USER_TOKEN` is set
4. Click "Redeploy" if needed

### Issue: Dashboard shows but chat doesn't work
**Cause:** Anthropic API key missing or invalid

**Fix:**
1. Check Railway logs for errors
2. Verify `ANTHROPIC_API_KEY` starts with `sk-ant-`
3. Test key at https://console.anthropic.com

### Issue: Slack data not loading
**Cause:** Slack token missing or expired

**Fix:**
1. Verify `SLACK_USER_TOKEN` starts with `xoxp-`
2. Check token hasn't expired
3. Regenerate if needed at https://api.slack.com/apps

---

## 📝 Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | ✅ Yes | Claude API key | `sk-ant-api03-...` |
| `CLIENT_NAME` | ✅ Yes | Client identifier | `youtube_agency` |
| `SLACK_USER_TOKEN` | ✅ Yes | Slack user token | `xoxp-...` |
| `CLIENT_API_KEY` | Optional | For external API access | Any secure string |
| `AIRTABLE_API_KEY` | Optional | For Airtable features | `pat...` |
| `GOOGLE_CREDENTIALS_JSON` | Optional | For Drive features | Base64 JSON |

---

## 🎊 You're Done!

Your PM Dashboard is now:
- ✅ Deployed to Railway
- ✅ Auto-authenticating
- ✅ Secure (server-side auth only)
- ✅ Ready to use immediately
- ✅ Auto-deploying from GitHub

Just share your Railway URL with your team and they can start using it right away!

---

**Railway URL Format:**
`https://samu-pm-agent-production.up.railway.app`

No setup. No configuration. Just works. 🚀
