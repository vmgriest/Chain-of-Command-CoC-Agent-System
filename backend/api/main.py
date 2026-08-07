"""FastAPI application.

    uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, WebSocket

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """TODO(M1): startup / shutdown.

    Startup:
      1. load_dotenv()
      2. get_config()  — fail fast and loudly on a bad config
      3. startup_checks() — warn about unpulled models, missing docs (M0)
      4. init_tracing() (M5)
      5. MCPRegistry().startup() (M3)
      6. build_graph() once and stash on app.state — compiling per request would
         re-spawn subprocesses and thrash

    Shutdown:
      - registry.shutdown() -> sandbox.shutdown_all()
      - close every open WebSocket cleanly
    """
    raise NotImplementedError
    yield  # noqa: unreachable until implemented


app = FastAPI(title="Chain of Command", lifespan=lifespan)

# TODO(M1): CORSMiddleware from the CORS_ORIGINS env var (Vite dev is :5173).


# --- HTTP -----------------------------------------------------------------

# TODO(M1): GET /api/health
#   Ollama reachable, Qdrant reachable, MCP server liveness, config loaded.

# TODO(M1): GET /api/config
#   Personas and themes for the frontend. ⚠ Public — never include MCP commands,
#   admin emails, scheduling links, or anything else from the private config.

# TODO(M5): GET /api/analytics — see backend/observability/tracing.py.


# --- WebSocket ------------------------------------------------------------


@app.websocket("/ws/chat/{session_id}")
async def chat(websocket: WebSocket, session_id: str) -> None:
    """TODO(M1): the main chat channel.

    Flow:
      1. accept()
      2. Resume from checkpoint if `session_id` is known; otherwise new_state().
         ⚠ On resume, if the graph is paused at an interrupt, RE-SEND the pending
           escalation_prompt / context_request. Otherwise a customer who
           refreshed sees a dead chat waiting on an answer to a question the UI
           no longer shows.
      3. Loop: receive a client event, dispatch:
           user_message        -> astream_events through the graph
           escalation_response -> Command(resume=approved)
           context_response    -> Command(resume=answer)
      4. Map graph events onto the wire protocol in backend/api/events.py.

    TODO(M1): stream tokens as they arrive — buffering until the turn completes
      makes a local 14B model feel broken.

    TODO(M1): on disconnect, do NOT tear down graph state. The checkpoint is the
      session; a dropped socket is not the end of a conversation.

    TODO(M5): auth. Sessions are currently anonymous and a session_id is
      guessable, so anyone with the id can read the conversation. Must be closed
      before any real deployment — see PLAN.md "Open items".
    """
    raise NotImplementedError


# TODO(M1): a ConnectionManager tracking session_id -> WebSocket, so the CEO's
#   human-escalation flow can push an event into a live session.
