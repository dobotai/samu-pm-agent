# Railway Deployment Guide

## ✅ GitHub Repository Connected!

Your code is now live at: **https://github.com/dobotai/samu-pm-agent**

---

## 🚀 Deploy to Railway (Step-by-Step)

### Step 1: Go to Railway
Open https://railway.app in your browser

### Step 2: Sign In
- Sign in with your GitHub account
- Authorize Railway to access your repositories

### Step 3: Create New Project
1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Choose **"dobotai/samu-pm-agent"**
4. Railway will automatically detect the configuration from `railway.json`

### Step 4: Set Environment Variables

Click on your project → **"Variables"** tab → Add these:

#### Required Variables:

```bash
# Anthropic API Key (REQUIRED)
ANTHROPIC_API_KEY=sk-ant-api03-YOUR_KEY_HERE

# Client Authentication (REQUIRED)
CLIENT_API_KEY=generate_a_random_32_char_key
CLIENT_NAME=youtube_agency

# Slack Integration (REQUIRED for Slack features)
SLACK_USER_TOKEN=xoxp-YOUR_SLACK_USER_TOKEN

# Airtable Integration (REQUIRED for Airtable features)
AIRTABLE_API_KEY=patXXXXXXXXXXXXXXXX

# Google Drive Integration (OPTIONAL)
GOOGLE_CREDENTIALS_JSON=base64_encoded_service_account_json
```

#### How to Generate CLIENT_API_KEY:
Run this in your terminal:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Or use any random string generator (minimum 32 characters).

### Step 5: Deploy

Railway will automatically:
1. ✅ Detect Python environment
2. ✅ Install dependencies from `requirements.txt`
3. ✅ Run health checks at `/health`
4. ✅ Start the server with `python execution/api_server.py`

Wait 2-3 minutes for deployment to complete.

### Step 6: Get Your Dashboard URL

Once deployed:
1. Click on your service
2. Go to **"Settings"** → **"Networking"**
3. Click **"Generate Domain"**
4. Your dashboard will be available at: `https://your-app.railway.app`

---

## 📝 Configure Your Dashboard

### Access the Dashboard
1. Go to your Railway URL: `https://your-app.railway.app`
2. Click the **⚙️ Settings** button (top right)
3. Enter your `CLIENT_API_KEY` (from Railway environment variables)
4. Click **Save**

### Start Using
You can now ask questions like:
- "Which editors are active today?"
- "Summarize the Taylor client channel"
- "Show me Suhaib's current workload"
- "Which clients need immediate attention?"

---

## 🔧 Railway Configuration Details

Railway uses these files for deployment:

### 1. railway.json
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python execution/api_server.py",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### 2. Procfile
```
web: python execution/api_server.py
```

### 3. requirements.txt
All Python dependencies are automatically installed.

---

## 🎯 Post-Deployment Checklist

After deployment, verify:

- [ ] **Health Check**: Visit `https://your-app.railway.app/health`
  - Should return: `{"status": "healthy", "service": "agent-api", "version": "1.0.0"}`

- [ ] **Dashboard Loads**: Visit `https://your-app.railway.app`
  - Should show the PM Dashboard interface

- [ ] **API Documentation**: Visit `https://your-app.railway.app/docs`
  - Should show FastAPI auto-generated docs

- [ ] **Chat Endpoint Works**: Test the chat interface
  - Enter API key in settings
  - Send a test message

---

## 🔐 Security Checklist

Before going live:

1. **Generate Strong API Key**
   - Use `secrets.token_urlsafe(32)` or similar
   - Never use `dev_test_key_12345` in production

2. **Rotate Anthropic API Key**
   - Create a new production key at https://console.anthropic.com
   - Different from development key

3. **Restrict CORS** (Optional)
   - Edit `execution/api_server.py`
   - Change `allow_origins=["*"]` to your specific domain

4. **Monitor Usage**
   - Check Railway logs regularly
   - Monitor Anthropic API usage
   - Review `.tmp/logs/` for agent activity

---

## 📊 Monitoring & Logs

### View Logs in Railway
1. Go to your project in Railway
2. Click on your service
3. Click **"Logs"** tab
4. View real-time server logs

### Check Agent Logs
Agent activity is logged to `.tmp/logs/` on the server:
- `approval_requests.jsonl` - Approval requests
- `{client_name}.jsonl` - Conversation logs

---

## 🔄 Continuous Deployment

Railway automatically redeploys when you push to GitHub:

```bash
# Make changes locally
git add .
git commit -m "Your change description"
git push origin main
```

Railway will:
1. Detect the push
2. Rebuild the application
3. Deploy automatically
4. Zero-downtime deployment

---

## 🛠️ Troubleshooting

### Issue: "Service Unhealthy"
**Solution:** Check environment variables are set correctly
```bash
# In Railway, verify all required variables exist:
ANTHROPIC_API_KEY
CLIENT_API_KEY
SLACK_USER_TOKEN
```

### Issue: "API Key Invalid"
**Solution:** Regenerate and update `CLIENT_API_KEY` in Railway

### Issue: "Slack Integration Not Working"
**Solution:**
1. Verify `SLACK_USER_TOKEN` starts with `xoxp-`
2. Check token has required scopes
3. Review Slack app configuration

### Issue: "Dashboard Not Loading"
**Solution:**
1. Check `/health` endpoint works
2. Verify `static/` directory is deployed
3. Check Railway logs for errors

---

## 💡 Tips & Best Practices

1. **Environment Separation**
   - Keep development `.env` separate from Railway variables
   - Use different API keys for dev/prod

2. **Cost Management**
   - Railway free tier: $5 credit/month
   - Monitor usage in Railway dashboard
   - Claude Opus 4.5 costs ~$15/1M input tokens

3. **Updates & Maintenance**
   - Test changes locally first
   - Use git branches for major changes
   - Railway auto-deploys from `main` branch

4. **Backup Strategy**
   - Conversation logs in `.tmp/logs/`
   - Export from Slack/Airtable regularly
   - Keep config files in version control

---

## 📞 Support Resources

- **Railway Documentation**: https://docs.railway.app
- **Anthropic API Docs**: https://docs.anthropic.com
- **FastAPI Docs**: https://fastapi.tiangolo.com
- **Project Repository**: https://github.com/dobotai/samu-pm-agent

---

## 🎉 You're All Set!

Your PM agent is now:
- ✅ Deployed to Railway
- ✅ Accessible via web dashboard
- ✅ Connected to Slack, Airtable, Drive
- ✅ Protected with API authentication
- ✅ Auto-deploying from GitHub

Open your dashboard and start managing your YouTube agency projects with AI! 🚀
