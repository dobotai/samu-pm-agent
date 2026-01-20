# Hosting Architecture: Claude Code CLI at Scale

## Current State

The webapp uses Claude Code CLI via subprocess for full agentic capabilities. This gives you:
- File operations (read, write, edit)
- Command execution (bash)
- Web tools (fetch, search)
- Session resumption (multi-turn conversations)
- All Claude Code capabilities

**Problem**: This approach has scaling limitations:
1. Sessions stored locally (don't scale across instances)
2. No token management or rate limiting
3. In-memory orchestrator state lost on restart
4. Subprocess overhead per request

## Optimized Architecture

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        LOAD BALANCER                            │
│                    (Railway or Cloudflare)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────▼─────┐    ┌─────▼─────┐    ┌─────▼─────┐
    │ Instance 1│    │ Instance 2│    │ Instance 3│
    │ api_server│    │ api_server│    │ api_server│
    └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
          │                │                │
          └────────────────┼────────────────┘
                           │
                    ┌──────▼──────┐
                    │   REDIS     │
                    │  (Upstash)  │
                    │ - Sessions  │
                    │ - Rate limits│
                    │ - Token usage│
                    └─────────────┘
```

### Components

#### 1. Redis Session Store (Upstash)
Store Claude Code session IDs in Redis instead of local files.

```python
# Session data structure in Redis
{
    "session:{client}:{user_id}": {
        "session_id": "uuid",
        "created": "ISO timestamp",
        "last_used": "ISO timestamp",
        "token_count": 12500,
        "turn_count": 7
    }
}
```

**Why Upstash?**
- Serverless Redis (pay per request)
- Works with Railway
- Automatic scaling
- ~$0.20/100K requests

#### 2. Token Tracking
Track token usage per session and per user.

```python
# Token tracking structure
{
    "tokens:{client}:{date}": {
        "input": 150000,
        "output": 25000,
        "cached": 100000
    },
    "tokens:{client}:{user_id}:{date}": {
        "input": 5000,
        "output": 1200
    }
}
```

**Key insight from research**: Cached input tokens don't count against rate limits on newer models. With 80% cache hit rate, you get 5x effective throughput.

#### 3. Rate Limiting
Implement per-user and per-client rate limits.

```python
# Rate limit tiers
RATE_LIMITS = {
    "free": {
        "requests_per_minute": 5,
        "tokens_per_day": 50000
    },
    "pro": {
        "requests_per_minute": 30,
        "tokens_per_day": 500000
    },
    "enterprise": {
        "requests_per_minute": 100,
        "tokens_per_day": 2000000
    }
}
```

#### 4. Request Queue (Optional)
For high-concurrency scenarios, queue requests to prevent overwhelming the API.

```
User Request → Queue (Redis) → Worker → Claude Code CLI → Response
```

This prevents:
- Subprocess exhaustion
- API rate limit hits
- Memory spikes from concurrent processes

### Implementation Changes

#### orchestrator.py Changes

```python
import redis
from datetime import datetime, timedelta

class ScopedOrchestrator:
    def __init__(self, client_name: str, user_id: str = "default"):
        self.client_name = client_name
        self.user_id = user_id

        # Redis connection (Upstash)
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            self.redis = redis.from_url(redis_url)
        else:
            self.redis = None  # Fall back to file-based

        # Load session from Redis
        self.session_id = self._load_session()

    def _load_session(self) -> Optional[str]:
        """Load session from Redis or file."""
        if self.redis:
            key = f"session:{self.client_name}:{self.user_id}"
            data = self.redis.hgetall(key)
            if data:
                created = datetime.fromisoformat(data.get("created", "2000-01-01"))
                if datetime.now() - created < timedelta(hours=1):
                    return data.get("session_id")
        # Fall back to file-based
        return self._load_session_from_file()

    def _save_session(self, session_id: str):
        """Save session to Redis."""
        if self.redis:
            key = f"session:{self.client_name}:{self.user_id}"
            self.redis.hset(key, mapping={
                "session_id": session_id,
                "created": datetime.now().isoformat(),
                "last_used": datetime.now().isoformat()
            })
            self.redis.expire(key, 3600)  # 1 hour TTL
        else:
            self._save_session_to_file(session_id)

    def _check_rate_limit(self) -> bool:
        """Check if user is within rate limits."""
        if not self.redis:
            return True

        key = f"ratelimit:{self.client_name}:{self.user_id}:{datetime.now().strftime('%Y%m%d%H%M')}"
        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, 60)  # Expire after 1 minute

        limit = 30  # requests per minute
        return count <= limit

    def _track_tokens(self, input_tokens: int, output_tokens: int):
        """Track token usage."""
        if not self.redis:
            return

        date = datetime.now().strftime('%Y%m%d')
        key = f"tokens:{self.client_name}:{date}"
        self.redis.hincrby(key, "input", input_tokens)
        self.redis.hincrby(key, "output", output_tokens)
        self.redis.expire(key, 86400 * 30)  # Keep 30 days
```

#### api_server.py Changes

```python
from fastapi import Request, HTTPException

# Add user identification
async def get_user_id(request: Request) -> str:
    """Extract user ID from request."""
    # From API key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"api:{api_key[:8]}"

    # From session cookie
    session = request.cookies.get("session_id")
    if session:
        return f"session:{session}"

    # From IP (fallback)
    return f"ip:{request.client.host}"

@app.post("/api/chat")
async def chat(request: ChatRequest, user_id: str = Depends(get_user_id)):
    # Get or create orchestrator with user context
    key = f"{request.client_name}:{user_id}"

    if key not in orchestrators:
        orchestrators[key] = ScopedOrchestrator(
            request.client_name,
            user_id=user_id
        )

    orchestrator = orchestrators[key]

    # Check rate limit
    if not orchestrator._check_rate_limit():
        raise HTTPException(429, "Rate limit exceeded")

    # Process request
    result = orchestrator.process_request(request.message)
    return ChatResponse(**result)
```

### Railway Configuration

#### Single Instance (Current)
- Works for low-to-medium traffic
- Session files work fine
- No Redis needed

#### Multi-Instance Scaling
For high traffic, deploy multiple instances with Redis:

**railway.json**:
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python execution/api_server.py",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5,
    "numReplicas": 3
  }
}
```

**Environment Variables**:
```
REDIS_URL=redis://default:xxx@xxx.upstash.io:6379
ANTHROPIC_API_KEY=sk-ant-xxx
CLIENT_NAME=youtube_agency
```

### Cost Optimization

#### 1. Model Selection
```python
# In orchestrator.py
def _get_model_for_request(self, message: str) -> str:
    """Choose optimal model based on request complexity."""
    # Simple queries → Haiku (cheapest)
    simple_patterns = ["list", "show", "what is", "how many"]
    if any(p in message.lower() for p in simple_patterns):
        return "haiku"

    # Complex analysis → Sonnet (balanced)
    return "sonnet"

    # Only use Opus for explicitly complex requests
```

#### 2. Prompt Caching
System prompts get cached after first use. With your detailed CLAUDE.md and client configs, you'll see significant cache hits.

**Expected savings**: 60-80% on input tokens for repeated system context.

#### 3. Session Timeout Tuning
- Short sessions (15 min) for simple Q&A
- Long sessions (1 hour) for complex workflows
- Configurable per client

### Monitoring

Add these metrics to track:
```python
# Log to Redis for monitoring
def _log_metrics(self, result):
    metrics = {
        "timestamp": datetime.now().isoformat(),
        "client": self.client_name,
        "user": self.user_id,
        "duration_ms": result.get("duration_ms", 0),
        "num_turns": result.get("num_turns", 1),
        "model": "sonnet",
        "success": not result.get("response", "").startswith("Error")
    }
    self.redis.rpush(f"metrics:{self.client_name}", json.dumps(metrics))
```

Dashboard queries:
- Requests per hour
- Average response time
- Token usage trends
- Error rates
- Popular queries

### Migration Path

1. **Phase 1**: Add Redis (Upstash) - sessions only
2. **Phase 2**: Add rate limiting and token tracking
3. **Phase 3**: Add request queuing for high load
4. **Phase 4**: Multi-instance deployment

### Alternative: Agent SDK

If the CLI subprocess approach becomes a bottleneck, consider migrating to the Agent SDK:

```python
from anthropic import Anthropic

client = Anthropic()

# Same capabilities, native Python
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=8096,
    tools=[...],  # Your tool definitions
    messages=[...]
)
```

**Trade-offs**:
- More control over tool execution
- No subprocess overhead
- But: must implement tool execution yourself
- Claude Code CLI handles complex agentic loops automatically

### Recommendation

For your current scale:
1. **Add Upstash Redis** - $0.20/100K requests
2. **Keep Claude Code CLI** - proven, full capabilities
3. **Add rate limiting** - prevent abuse
4. **Monitor token usage** - track costs

This gives you:
- Multi-instance capability when needed
- Cost visibility
- User isolation
- Protection against abuse

The Agent SDK migration is only needed if subprocess overhead becomes the bottleneck (typically >100 concurrent users).
