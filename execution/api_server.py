#!/usr/bin/env python3
"""
API Server: Web interface for client agents
Handles authentication, routing, and orchestrator coordination
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import ScopedOrchestrator


app = FastAPI(
    title="Agent API",
    version="1.0.0",
    description="Scoped autonomous agent API for client businesses"
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
# TODO: Use Redis or similar for production multi-instance deployments
orchestrators: Dict[str, ScopedOrchestrator] = {}


# Request/Response Models
class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str
    client_name: Optional[str] = None
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    response: str
    tools_used: List[dict]
    conversation_id: str


class ToolInfo(BaseModel):
    """Tool information model"""
    name: str
    description: str


class ToolsResponse(BaseModel):
    """Response model for tools endpoint"""
    tools: List[ToolInfo]


# Authentication
def verify_api_key(x_api_key: str = Header(...)) -> str:
    """
    Verify client API key and return client name.

    Args:
        x_api_key: API key from request header

    Returns:
        Client name if authenticated

    Raises:
        HTTPException: If authentication fails
    """
    expected_key = os.getenv("CLIENT_API_KEY")

    if not expected_key:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: CLIENT_API_KEY not set"
        )

    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Get client name from environment
    client_name = os.getenv("CLIENT_NAME", "default_client")
    return client_name


# Endpoints
@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    client_name: str = Depends(verify_api_key)
):
    """
    Main chat endpoint - send natural language request to agent.

    Args:
        request: Chat request with message
        client_name: Client name from authentication

    Returns:
        Chat response with agent's reply and tools used

    Raises:
        HTTPException: If client config not found or processing error
    """
    try:
        # Use client_name from request if provided, otherwise from auth
        target_client = request.client_name or client_name

        # Get or create orchestrator for this client
        if target_client not in orchestrators:
            orchestrators[target_client] = ScopedOrchestrator(target_client)

        orchestrator = orchestrators[target_client]

        # Process request
        result = orchestrator.process_request(request.message)

        return ChatResponse(**result)

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Client configuration not found for: {client_name}"
        )
    except Exception as e:
        # Log error but don't expose internal details
        print(f"Error processing request: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error processing request"
        )


@app.get("/api/chat/history")
async def get_history(client_name: str = Depends(verify_api_key)):
    """
    Retrieve conversation history for client.

    Args:
        client_name: Client name from authentication

    Returns:
        Dict with conversation history
    """
    if client_name not in orchestrators:
        return {"history": []}

    orchestrator = orchestrators[client_name]
    return {"history": orchestrator.conversation_history}


@app.get("/api/tools", response_model=ToolsResponse)
async def list_tools(client_name: str = Depends(verify_api_key)):
    """
    List available tools for transparency.

    Args:
        client_name: Client name from authentication

    Returns:
        List of available tools with descriptions
    """
    try:
        # Create temporary orchestrator to get config
        orchestrator = ScopedOrchestrator(client_name)

        tools = [
            ToolInfo(
                name=tool["name"],
                description=tool["description"]
            )
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
    """
    Health check endpoint for Railway and monitoring.

    Returns:
        Status dict
    """
    return {
        "status": "healthy",
        "service": "agent-api",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """
    Serve the dashboard HTML.

    Returns:
        HTML file response
    """
    static_dir = Path(__file__).parent.parent / "static"
    index_file = static_dir / "index.html"

    if index_file.exists():
        return FileResponse(index_file)
    else:
        # Fallback to API info if dashboard not found
        return {
            "service": "Agent API",
            "version": "1.0.0",
            "endpoints": {
                "chat": "POST /api/chat",
                "history": "GET /api/chat/history",
                "tools": "GET /api/tools",
                "health": "GET /health"
            },
            "documentation": "/docs"
        }


if __name__ == "__main__":
    import uvicorn

    # Get port from environment (Railway sets PORT)
    port = int(os.getenv("PORT", 8000))

    # Get host from environment
    host = os.getenv("HOST", "0.0.0.0")

    print(f"Starting Agent API server on {host}:{port}")
    print(f"Documentation available at http://{host}:{port}/docs")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )
