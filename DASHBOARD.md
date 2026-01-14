# PM Dashboard Documentation

## Overview

The PM Dashboard is a web-based interface that allows project managers to interact with the YouTube Agency autonomous agent through natural language. It provides real-time access to Slack, Airtable, and Google Drive data without needing to use the command line.

## Features

### 🎯 Natural Language Chat Interface
- Ask questions in plain English
- Get intelligent responses from the agent
- View conversation history

### ⚡ Quick Actions Sidebar
Pre-built queries for common tasks:
- "Which editors are active today?"
- "Which clients need immediate attention?"
- "Show me all projects due this week"
- "Summarize Taylor client channel"
- "List all channels"

### 🔒 Security
- API key authentication
- Encrypted communication
- Session-based access control

### 📊 Real-time Data Access
- **Slack**: Read messages, channels, users
- **Airtable**: Access project records
- **Google Drive**: View files and folders

## Local Development

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Edit `.env` file:
```bash
ANTHROPIC_API_KEY=your_anthropic_api_key
CLIENT_API_KEY=your_dashboard_api_key
CLIENT_NAME=youtube_agency
SLACK_USER_TOKEN=your_slack_token
AIRTABLE_API_KEY=your_airtable_key
```

### 3. Start the Server
```bash
python execution/api_server.py
```

The dashboard will be available at: http://localhost:8000

### 4. Access the Dashboard
1. Open http://localhost:8000 in your browser
2. Click the ⚙️ Settings button
3. Enter your `CLIENT_API_KEY` from the `.env` file
4. Save settings
5. Start chatting!

## Railway Deployment

### Deploy to Railway

1. **Connect Repository**
   - Go to https://railway.app
   - Create new project from GitHub repo
   - Railway will auto-detect the configuration

2. **Set Environment Variables**
   In Railway dashboard, add:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   CLIENT_API_KEY=generate_random_key_here
   CLIENT_NAME=youtube_agency
   SLACK_USER_TOKEN=xoxp-...
   AIRTABLE_API_KEY=pat...
   AIRTABLE_BASE_ID=app...
   GOOGLE_CREDENTIALS_JSON=base64_encoded_json
   ```

3. **Deploy**
   - Railway auto-deploys on push to main branch
   - Health check endpoint: `/health`
   - Dashboard URL: `https://your-app.railway.app`

4. **Access Deployed Dashboard**
   - Navigate to your Railway app URL
   - Enter API key in settings
   - Start using the dashboard!

## Usage Examples

### Example Queries

**Project Management:**
- "Which editors are active today?"
- "Show me Suhaib's current workload"
- "What projects are due this week?"
- "List all overdue tasks"

**Client Communication:**
- "Summarize the Taylor client channel"
- "Show me recent messages from #nicolas-client"
- "Which clients haven't been updated this week?"
- "What's the status of the Hiver project?"

**Team Coordination:**
- "Send a message to Suhaib about the deadline"
- "Who's working on Dan's videos?"
- "Show me all editing channels"
- "Which editors need assignments?"

**Data Analysis:**
- "How many videos did we complete this month?"
- "What's the average turnaround time?"
- "Show me all blocked projects"
- "Which clients are most active?"

## Dashboard Structure

```
static/
├── index.html          # Main dashboard HTML
├── css/
│   └── style.css      # Dashboard styling
└── js/
    └── app.js         # Dashboard JavaScript logic

execution/
└── api_server.py      # FastAPI server serving dashboard
```

## API Endpoints

### POST /api/chat
Send a message to the agent.

**Request:**
```json
{
  "message": "Which editors are active today?",
  "client_name": "youtube_agency"
}
```

**Response:**
```json
{
  "response": "12 editors are active today...",
  "tools_used": [...],
  "conversation_id": "uuid"
}
```

### GET /api/chat/history
Retrieve conversation history.

**Response:**
```json
{
  "history": [...]
}
```

### GET /api/tools
List available tools.

**Response:**
```json
{
  "tools": [
    {
      "name": "slack_read_messages",
      "description": "Read messages from Slack channel"
    },
    ...
  ]
}
```

### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "agent-api",
  "version": "1.0.0"
}
```

## Security Best Practices

1. **API Key Management**
   - Generate strong random API keys
   - Rotate keys regularly
   - Never commit keys to Git

2. **Production Deployment**
   - Use HTTPS only
   - Restrict CORS origins
   - Enable rate limiting
   - Add request logging

3. **Environment Variables**
   - Never expose in client-side code
   - Use Railway's secret management
   - Separate dev and prod keys

## Troubleshooting

### Dashboard Not Loading
1. Check that `static/` directory exists
2. Verify API server is running
3. Check browser console for errors

### API Key Not Working
1. Verify key matches `.env` file
2. Check that `CLIENT_API_KEY` is set
3. Try clearing browser localStorage

### Agent Not Responding
1. Check `ANTHROPIC_API_KEY` is valid
2. Verify client config exists: `config/clients/youtube_agency.json`
3. Check server logs for errors

### Tools Not Working
1. Verify all API keys are set (Slack, Airtable, etc.)
2. Check token permissions/scopes
3. Review logs in `.tmp/logs/`

## Customization

### Adding Quick Actions
Edit `static/index.html`:
```html
<button class="action-btn" onclick="quickQuery('Your query here')">
    🔍 Your Action
</button>
```

### Changing Theme Colors
Edit `static/css/style.css`:
```css
:root {
    --primary-color: #4f46e5;  /* Change this */
    --bg-primary: #0f172a;     /* And this */
}
```

### Adding New Features
1. Update `static/js/app.js` for frontend logic
2. Update `execution/api_server.py` for backend endpoints
3. Test locally before deploying

## Support

For issues or questions:
1. Check logs: `.tmp/logs/`
2. Review [SAFETY_GUARDRAILS.md](SAFETY_GUARDRAILS.md)
3. Check agent logs for tool execution errors

---

**Built with:**
- FastAPI (Backend)
- Vanilla JS (Frontend)
- Anthropic Claude Opus 4.5 (AI Agent)
- Railway (Hosting)
