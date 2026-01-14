# DOEBI Agent Infrastructure

Automation agency infrastructure for building and deploying scoped autonomous agents for client businesses.

## Overview

This system implements the **DOEBI architecture** (Directives, Orchestration, Execution, Business, Interface) - a framework that separates concerns to maximize reliability while being client-deployable.

**What it does:**
- Builds scoped autonomous agents for clients
- Agents use natural language to interact with clients
- Agents use predefined tools creatively within boundaries
- Agents recommend new tools when functionality is missing
- You maintain full control via Git and configuration files

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Edit `.env` and add your API keys:

```bash
ANTHROPIC_API_KEY=your_anthropic_api_key_here
CLIENT_API_KEY=your_client_api_key_here
CLIENT_NAME=example_client
```

### 3. Test Locally

Start the API server:

```bash
python execution/api_server.py
```

The server will start on `http://localhost:8000`

Access the interactive API docs at: `http://localhost:8000/docs`

### 4. Test the Agent

Send a chat request:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_client_api_key_here" \
  -d '{"message": "What time is it?"}'
```

## Directory Structure

```
.
├── directives/           # Layer D: SOPs and workflows (Markdown)
├── execution/            # Layer E: Deterministic tools (Python scripts)
│   ├── orchestrator.py   # Autonomous agent engine
│   ├── api_server.py     # Web server for client endpoints
│   └── tools/            # Individual tool scripts
├── config/               # Client configurations
│   └── clients/          # Per-client config files
├── .tmp/                 # Temporary files (not committed)
│   └── logs/             # Conversation logs
├── .env                  # Environment variables (not committed)
├── requirements.txt      # Python dependencies
├── Procfile              # Railway start command
└── railway.json          # Railway deployment config
```

## The DOEBI Architecture

### D - Directives
- SOPs written in Markdown in `directives/`
- Define goals, inputs, tools, outputs, edge cases
- Living documents that improve over time

### O - Orchestration
- **Dev Mode**: You manually orchestrate via this terminal
- **Client Mode**: `orchestrator.py` autonomously decides which tools to use

### E - Execution
- Deterministic Python scripts in `execution/`
- One responsibility per script
- Return JSON to stdout
- Handle errors gracefully

### B - Business
- Your agency operations
- Build toolkits for clients
- Monitor and expand capabilities
- Revenue from tool recommendations → building → upsells

### I - Interface
- Client-facing natural language chat
- API endpoints: `/api/chat`, `/api/tools`, `/api/chat/history`
- No code access for clients
- Agent recommends missing tools

## Building for a Client

### 1. Discovery
Understand their domain, pain points, desired capabilities.

### 2. Build Toolkit
Create execution scripts for their needs:
```bash
execution/tools/read_sheet.py
execution/tools/update_sheet.py
execution/tools/send_email.py
```

### 3. Define Agent
Create `config/clients/{client_name}.json`:

```json
{
  "client_name": "acme_corp",
  "agent_type": "project_management",
  "system_prompt": "You are a project management assistant for Acme Corp...",
  "available_tools": [
    {
      "name": "read_tasks",
      "script": "execution/tools/read_sheet.py",
      "description": "Read tasks from project tracker",
      "input_schema": {
        "type": "object",
        "properties": {
          "sheet_id": {"type": "string"}
        },
        "required": ["sheet_id"]
      }
    }
  ],
  "constraints": [
    "Cannot delete data",
    "Read-only access to financial sheets"
  ]
}
```

### 4. Test Locally
Simulate client requests in dev mode.

### 5. Deploy to Railway

#### Setup:
1. Connect Railway to your Git repository
2. Configure environment variables in Railway dashboard:
   - `ANTHROPIC_API_KEY`
   - `CLIENT_API_KEY`
   - `CLIENT_NAME`
   - `GOOGLE_CREDENTIALS_JSON` (base64 encoded)
   - Any client-specific API keys

3. Railway auto-deploys on git push

#### Environment Variables:
Set these in Railway dashboard:
- `ANTHROPIC_API_KEY` - For Claude Opus 4.5 orchestration
- `CLIENT_API_KEY` - For client authentication
- `CLIENT_NAME` - Client identifier
- `GOOGLE_CREDENTIALS_JSON` - Base64-encoded credentials
- `SLACK_WEBHOOK_URL` - For notifications (optional)

### 6. Monitor & Expand
- Review logs in `.tmp/logs/{client_name}.jsonl`
- Agent recommends missing tools
- Build valuable tools
- Update config, push to Git
- Railway auto-deploys with new capabilities

## API Endpoints

### POST /api/chat
Send natural language request to agent.

**Headers:**
- `X-API-Key`: Client API key

**Request:**
```json
{
  "message": "What tasks are blocked?"
}
```

**Response:**
```json
{
  "response": "There are 3 blocked tasks: [details]",
  "tools_used": [...],
  "conversation_id": "client_2025-01-09T..."
}
```

### GET /api/tools
List available tools for client.

### GET /api/chat/history
Get conversation history.

### GET /health
Health check endpoint for Railway.

## Operating Principles

### 1. Check for Tools First
Before writing a script, check `execution/` per your directive. Only create new scripts if none exist.

### 2. Self-Anneal When Things Break
- Read error message and stack trace
- Fix the script and test it
- Update the directive with learnings

### 3. Update Directives as You Learn
Directives are living documents. Update them with API constraints, better approaches, common errors, timing expectations.

### 4. Self-Annealing Loop
When something breaks:
1. Fix it
2. Update the tool
3. Test tool
4. Update directive
5. System is now stronger

## File Organization

**Deliverables vs Intermediates:**
- **Deliverables**: Google Sheets, Slides, or cloud-based outputs clients access
- **Intermediates**: Temporary files in `.tmp/` (never committed)

**Key principle:** Local files are only for processing. Deliverables live in cloud services where clients access them.

## Example Client Interaction

```
Client: "What tasks are blocked?"
Agent: Uses read_tasks tool → filters for blocked → returns results

Client: "Assign task #47 to Sarah"
Agent: Uses assign_task tool → confirms completion

Client: "Can you integrate with Jira?"
Agent: "I don't currently have Jira integration. I would need a 'sync_jira' tool that could:
- Read tasks from your Jira board
- Sync status between systems
I've logged this as a feature request for your agency contact."
```

## Development Workflow

### Testing Orchestrator Directly
```bash
python execution/orchestrator.py example_client "What time is it?"
```

### Running API Server Locally
```bash
python execution/api_server.py
# Server starts on http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Creating New Tools
1. Create script in `execution/tools/your_tool.py`
2. Script must output JSON to stdout
3. Add to client config `available_tools` array
4. Test locally
5. Deploy

## Troubleshooting

### Agent not responding
- Check `ANTHROPIC_API_KEY` is set
- Check client config exists: `config/clients/{client_name}.json`
- Check logs: `.tmp/logs/{client_name}.jsonl`

### Tool execution failing
- Tool scripts must output JSON to stdout
- Tool scripts must exit with code 0 on success
- Check tool script has execute permissions
- Test tool directly: `python execution/tools/your_tool.py`

### Authentication errors
- Verify `CLIENT_API_KEY` matches in `.env` and request header
- Verify `CLIENT_NAME` is set correctly

## Learn More

See [CLAUDE.md](CLAUDE.md) for complete architecture documentation and operating principles.

## License

Proprietary - Automation Agency Infrastructure

---

**Built with the DOEBI Architecture**
*Directives • Orchestration • Execution • Business • Interface*
