#!/usr/bin/env python3
"""
API Server: Web interface for client agents + automation dashboard
Handles authentication, routing, orchestrator coordination, and scheduler lifecycle
"""

import asyncio
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import ScopedOrchestrator
from scheduler import AutomationScheduler


app = FastAPI(
    title="Agent API",
    version="2.0.0",
    description="Scoped autonomous agent API with automation scheduler"
)

# CORS for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for dashboard
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# In-memory orchestrator instances
orchestrators: Dict[str, ScopedOrchestrator] = {}

# Automation scheduler
automation_scheduler = AutomationScheduler(
    config_path=str(Path(__file__).parent.parent / "config" / "automations.json")
)


# ------------------------------------------------------------------
# Lifecycle Events
# ------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Start the automation scheduler on server boot."""
    try:
        await automation_scheduler.start()
    except Exception as e:
        print(f"[API] Warning: Scheduler failed to start: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shut down the scheduler gracefully."""
    await automation_scheduler.shutdown()


# ------------------------------------------------------------------
# Request/Response Models
# ------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    client_name: Optional[str] = None
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    tools_used: List[dict]
    conversation_id: str


class ToolInfo(BaseModel):
    name: str
    description: str


class ToolsResponse(BaseModel):
    tools: List[ToolInfo]


class ToggleRequest(BaseModel):
    enabled: bool


# ------------------------------------------------------------------
# Authentication
# ------------------------------------------------------------------

def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verify client API key and return client name."""
    expected_key = os.getenv("CLIENT_API_KEY")

    if x_api_key:
        if not expected_key:
            raise HTTPException(
                status_code=500,
                detail="Server configuration error: CLIENT_API_KEY not set"
            )
        if x_api_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

    client_name = os.getenv("CLIENT_NAME", "youtube_agency")
    return client_name


# ------------------------------------------------------------------
# Dashboard Routes
# ------------------------------------------------------------------

@app.get("/")
async def root():
    """Serve the automation dashboard."""
    dashboard_file = static_dir / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(dashboard_file)
    # Fallback to old index.html
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "service": "Agent API",
        "version": "2.0.0",
        "dashboard": "Dashboard HTML not found. Place dashboard.html in static/",
        "endpoints": {
            "automations": "GET /api/automations",
            "chat": "POST /api/chat",
            "health": "GET /health",
        },
    }


@app.get("/chat")
async def chat_page():
    """Serve the original chat interface."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Chat page not found")


# ------------------------------------------------------------------
# Automation API Endpoints
# ------------------------------------------------------------------

@app.get("/api/automations")
async def list_automations():
    """Get all automations with their current status."""
    return automation_scheduler.get_status()


@app.get("/api/automations/{automation_id}")
async def get_automation(automation_id: str):
    """Get single automation status."""
    result = automation_scheduler.get_automation_status(automation_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Automation not found: {automation_id}")
    return result


@app.get("/api/automations/{automation_id}/history")
async def get_automation_history(automation_id: str, limit: int = Query(20, ge=1, le=100)):
    """Get run history for an automation."""
    auto = automation_scheduler._find_automation(automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail=f"Automation not found: {automation_id}")
    return {
        "automation_id": automation_id,
        "entries": automation_scheduler.get_run_history(automation_id, limit),
    }


@app.post("/api/automations/{automation_id}/trigger")
async def trigger_automation(automation_id: str):
    """Manually trigger an automation."""
    auto = automation_scheduler._find_automation(automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail=f"Automation not found: {automation_id}")

    state = automation_scheduler.run_state.get(automation_id, {})
    if state.get("currently_running"):
        raise HTTPException(status_code=409, detail="Automation is already running")

    asyncio.create_task(automation_scheduler.run_automation(automation_id, triggered_by="manual"))
    return {"status": "triggered", "automation_id": automation_id}


@app.post("/api/automations/{automation_id}/toggle")
async def toggle_automation(automation_id: str, body: ToggleRequest):
    """Enable or disable an automation."""
    auto = automation_scheduler._find_automation(automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail=f"Automation not found: {automation_id}")

    if body.enabled:
        automation_scheduler.enable_automation(automation_id)
    else:
        automation_scheduler.disable_automation(automation_id)

    return {"automation_id": automation_id, "enabled": body.enabled}


# ------------------------------------------------------------------
# Chat API Endpoints (existing)
# ------------------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    client_name: str = Depends(verify_api_key)
):
    """Main chat endpoint - send natural language request to agent."""
    try:
        target_client = request.client_name or client_name

        if target_client not in orchestrators:
            orchestrators[target_client] = ScopedOrchestrator(target_client)

        orchestrator = orchestrators[target_client]
        result = await orchestrator.process_request(request.message)
        return ChatResponse(**result)

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Client configuration not found for: {client_name}"
        )
    except Exception as e:
        print(f"Error processing request: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error processing request"
        )


@app.get("/api/chat/history")
async def get_history(client_name: str = Depends(verify_api_key)):
    """Retrieve conversation history for client."""
    if client_name not in orchestrators:
        return {"history": []}
    orchestrator = orchestrators[client_name]
    return {"history": orchestrator.conversation_history}


@app.get("/api/tools", response_model=ToolsResponse)
async def list_tools(client_name: str = Depends(verify_api_key)):
    """List available tools for transparency."""
    try:
        orchestrator = ScopedOrchestrator(client_name)
        tools = [
            ToolInfo(name=tool["name"], description=tool["description"])
            for tool in orchestrator.available_tools
        ]
        return ToolsResponse(tools=tools)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Client configuration not found for: {client_name}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint for Railway and monitoring."""
    return {
        "status": "healthy",
        "service": "agent-api",
        "version": "2.0.0",
        "scheduler_running": bool(
            automation_scheduler.scheduler and automation_scheduler.scheduler.running
        ),
    }


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")

    print(f"Starting Agent API server on {host}:{port}")
    print(f"Dashboard:     http://{host}:{port}/")
    print(f"Chat UI:       http://{host}:{port}/chat")
    print(f"API docs:      http://{host}:{port}/docs")
    print(f"Automations:   http://{host}:{port}/api/automations")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )
