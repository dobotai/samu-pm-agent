# Agent Instructions
> This file is mirrored across CLAUDE.md, AGENTS.md, and GEMINI.md so the same instructions load in any AI environment.

## System Purpose
This is an **automation agency infrastructure** designed to build and deploy scoped autonomous agents for client businesses. The DOEBI architecture separates concerns to maximize reliability while being client-deployable. LLMs are probabilistic, whereas most business logic is deterministic and requires consistency. This system fixes that mismatch.

**Why this works:** if you do everything yourself, errors compound. 90% accuracy per step = 59% success over 5 steps. The solution: push complexity into deterministic code. That way you just focus on decision-making.

## The DOEBI Architecture

### D - Directives (What to do)
**Layer 1: Instructions and workflows**
- SOPs written in Markdown, live in `directives/`
- Define goals, inputs, tools/scripts to use, outputs, and edge cases
- Natural language instructions, like you'd give a mid-level employee
- Living documents that improve over time with learnings
- Optional: client-specific subdirectories `directives/client_name/`

**When to use directives:**
- Complex multi-step workflows that need documentation
- Processes that will be repeated or refined over time
- Standard operating procedures for common tasks

### O - Orchestration (Decision making)
**Layer 2: Intelligent routing and coordination**

**Two modes:**

**Development Mode (this environment):**
- You (human + Claude Code) are the orchestrator
- Read directives, call execution tools in the right order
- Handle errors, ask for clarification, update directives with learnings
- You're the glue between intent and execution
- Example: you read `directives/scrape_website.md` → run `execution/scrape_single_site.py`

**Client Mode (deployed instances):**
- `execution/orchestrator.py` is the autonomous orchestrator
- Reads client config (`config/clients/{name}.json`)
- Receives natural language requests from clients
- Calls Claude API (Opus 4.5) to decide which tools to use
- Executes tools autonomously
- Handles errors with self-annealing
- Logs all interactions

**Key difference:** In dev mode, you manually orchestrate. In client mode, orchestrator.py autonomously decides which tools to use based on natural language requests.

### E - Execution (Doing the work)
**Layer 3: Deterministic tools**
- Python scripts in `execution/`
- Handle API calls, data processing, file operations, database interactions
- Reliable, testable, fast
- Environment variables and API tokens stored in `.env`

**Core execution files:**
- `execution/orchestrator.py` - Autonomous agent engine (client mode)
- `execution/api_server.py` - Web server for client endpoints
- Individual tool scripts (read_sheet.py, send_email.py, etc.)

**Execution principles:**
- One responsibility per script
- Accept parameters via command-line arguments
- Return structured data (JSON preferred)
- Handle errors gracefully
- Write intermediate outputs to `.tmp/`

### B - Business (Agency operations)
**Your side: Building and delivering agents**

**Client onboarding workflow:**
1. **Discovery**: Understand client's domain, pain points, desired capabilities
2. **Build Toolkit**: Create execution scripts for their specific needs
3. **Define Agent**: Write `config/clients/{client_name}.json` with tools, system prompt, constraints
4. **Test Locally**: Simulate client requests in dev mode
5. **Deploy**: Push to Railway → auto-deploys
6. **Monitor & Expand**: Review logs, build new tools, update capabilities

**What you maintain:**
- Full control over toolkit (execution scripts) via Git
- Ability to add new capabilities anytime
- Complete conversation and tool usage logs
- Self-annealing system that improves over time
- Reusable tools across similar clients
- Clear visibility into what clients need next (via agent recommendations)

**Revenue model:**
- Agent recommends missing tools
- You build valuable ones
- Client capabilities expand
- Recurring upsell opportunities

### I - Interface (Client-facing)
**Their side: Using the agent**

**Client experience:**
- Natural language chat interface (web UI or API)
- Ask any question or give any command within scope
- Agent uses tools creatively to solve novel problems
- Conversational, flexible, intelligent
- When functionality is missing, agent recommends new tools
- No code visibility, just intelligent assistance

**API Endpoints:**
- `POST /api/chat` - Send natural language requests to agent
- `GET /api/chat/history` - Retrieve conversation history
- `GET /api/tools` - List available tools (transparency)
- `GET /health` - Health check (Railway)

**Example interactions:**
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

**Boundaries & Safety:**
- **Tool Whitelist**: Agent can only use tools in client config
- **System Prompt**: Defines role, personality, boundaries
- **Constraints**: Explicit rules (e.g., "cannot delete data")
- **Authentication**: API keys or JWT tokens
- **No Code Access**: Clients cannot view or modify infrastructure
- **Logging**: All conversations and tool usage logged

## Operating Principles

**1. Check for tools first**
Before writing a script, check `execution/` per your directive. Only create new scripts if none exist.

**2. Self-anneal when things break**
- Read error message and stack trace
- Fix the script and test it again (unless it uses paid tokens/credits—check with user first)
- Update the directive with what you learned (API limits, timing, edge cases)
- Example: hit API rate limit → find batch endpoint → rewrite script → test → update directive

**3. Update directives as you learn**
Directives are living documents. When you discover API constraints, better approaches, common errors, or timing expectations—update the directive. But don't create or overwrite directives without asking unless explicitly told to.

**4. Self-annealing loop**
When something breaks:
1. Fix it
2. Update the tool
3. Test tool, make sure it works
4. Update directive to include new flow
5. System is now stronger

## File Organization

**Deliverables vs Intermediates:**
- **Deliverables**: Google Sheets, Google Slides, or cloud-based outputs clients access
- **Intermediates**: Temporary files needed during processing

**Directory structure:**
- `.tmp/` - All intermediate files. Never commit, always regenerated
- `execution/` - Python scripts (deterministic tools)
  - `api_server.py` - Web server for client endpoints
  - `orchestrator.py` - Autonomous agent engine
  - Individual tool scripts
- `directives/` - SOPs in Markdown (instruction set)
  - Optional: `directives/client_name/` subdirectories
- `config/` - Client configuration files
  - `clients/{client_name}.json` - Per-client: tools, system prompt, constraints, credentials
- `.env` - Environment variables and API keys (development only)
- `credentials.json`, `token.json` - Google OAuth credentials (in `.gitignore`)

**Key principle:** Local files are only for processing. Deliverables live in cloud services (Google Sheets, Slides, etc.) where clients access them. Everything in `.tmp/` can be deleted and regenerated.

## Infrastructure Components

### Client Configuration
Each client gets `config/clients/{client_name}.json` with:
- `client_name` - Identifier
- `agent_type` - Domain (e.g., "project_management", "sales", "hr")
- `system_prompt` - Agent personality, role, and boundaries
- `available_tools` - Array of tools with name, script path, description, parameters
- `constraints` - Array of explicit rules (e.g., "cannot delete data")
- `output_destinations` - Where results go (sheets, emails, webhooks)

### Orchestrator (execution/orchestrator.py)
**Purpose:** Autonomous agent engine for client mode

**Key responsibilities:**
- Load client config on initialization
- Process natural language requests from clients
- Call Claude API (Opus 4.5) with tools and system prompt
- Execute tools via subprocess (runs execution scripts)
- Maintain conversation history
- Handle errors and timeouts
- Log all interactions to `.tmp/logs/{client_name}.jsonl`

**Core methods:**
- `process_request(user_message)` - Main entry point
- `_build_system_prompt()` - Combines system prompt + constraints
- `_build_tool_definitions()` - Converts config tools to Claude API format
- `_process_response()` - Handles tool calls from Claude
- `_execute_tool()` - Runs execution scripts via subprocess
- `_log_interaction()` - Logs to file

### API Server (execution/api_server.py)
**Purpose:** Web interface for client agents

**Tech stack:** FastAPI + uvicorn

**Endpoints:**
- `POST /api/chat` - Main chat endpoint (requires API key)
- `GET /api/chat/history` - Conversation history
- `GET /api/tools` - List available tools
- `GET /health` - Health check for Railway

**Key features:**
- API key authentication via header
- CORS middleware for web UI
- Orchestrator instance management (in-memory, use Redis in production)
- Error handling with proper HTTP status codes

### Railway Deployment

**Required files:**
- `Procfile` - Start command: `web: python execution/api_server.py`
- `railway.json` - Build and deploy config (NIXPACKS, health check, restart policy)
- `requirements.txt` - Python dependencies (anthropic, fastapi, uvicorn, etc.)

**Environment variables:**
- `ANTHROPIC_API_KEY` - For Claude Opus 4.5
- `CLIENT_API_KEY` - For client authentication
- `CLIENT_NAME` - Client identifier
- `GOOGLE_CREDENTIALS_JSON` - Base64-encoded credentials
- `GOOGLE_TOKEN_JSON` - Base64-encoded token (optional)
- `SLACK_WEBHOOK_URL` - For notifications
- Client-specific API keys as needed

**Deployment workflow:**
1. Build toolkit (execution scripts)
2. Define agent (client config)
3. Test locally
4. Commit to Git
5. Connect Railway to repo
6. Set environment variables
7. Railway auto-deploys
8. Client gets access

## Dependencies (requirements.txt)

**Core:**
- anthropic>=0.18.0
- fastapi>=0.104.0
- uvicorn[standard]>=0.24.0
- pydantic>=2.0.0

**Google APIs:**
- google-auth>=2.23.0
- google-auth-oauthlib>=1.1.0
- google-auth-httplib2>=0.1.1
- google-api-python-client>=2.100.0

**Utilities:**
- python-dotenv>=1.0.0
- requests>=2.31.0
- pandas>=2.1.0
- openpyxl>=3.1.0
- sendgrid>=6.10.0
- python-dateutil>=2.8.2
- pytz>=2023.3

## Summary

**In Development Mode (this environment):**
You build the agent's toolkit. You sit between human intent and deterministic execution. You create execution scripts, define agent configurations, test workflows, and continuously improve the system. Your job: build the intelligence that will run autonomously.

**In Client Mode (deployed instances):**
The orchestrator.py agent operates autonomously within a scoped toolkit. It sits between client natural language requests and deterministic execution scripts. The agent:
- Receives requests in natural language
- Decides which tools to use (from available toolkit)
- Executes tools creatively to solve problems
- Chains tools together for complex workflows
- Explains limitations when out of scope
- Recommends new tools when functionality is missing
- Self-anneals when errors occur
- Maintains conversational context

**The value proposition:**
Clients get an autonomous AI assistant tailored to their domain. Not just automation scripts, but an intelligent agent that understands their business and uses tools creatively. When they need new capabilities, the agent identifies gaps and you build them. The system gets smarter over time while you maintain full control.

Be pragmatic. Be reliable. Self-anneal.

Also, use Opus-4.5 for everything while building. It came out a few days ago and is an order of magnitude better than Sonnet and other models. If you can't find it, look it up first.
