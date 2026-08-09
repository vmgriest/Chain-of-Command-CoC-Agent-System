"""FastAPI application.

    uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.api.events import (
    ContextResponse,
    ErrorEvent,
    EscalationResponse,
    TokenEvent,
    UserMessage,
    parse_client_event,
)
from backend.config.loader import get_config, startup_checks
from backend.config.schema import Tier

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger("coc.api")


class ConnectionManager:
    """Tracks session_id -> live WebSocket so a server-initiated event (e.g. the
    CEO's human-escalation push in M4) can reach an already-open connection."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    def register(self, session_id: str, websocket: WebSocket) -> None:
        self._connections[session_id] = websocket

    def unregister(self, session_id: str, websocket: WebSocket) -> None:
        if self._connections.get(session_id) is websocket:
            del self._connections[session_id]

    def get(self, session_id: str) -> WebSocket | None:
        return self._connections.get(session_id)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown.

    Startup:
      1. load_dotenv()
      2. get_config()  — fail fast and loudly on a bad config
      3. startup_checks() — warn about unpulled models, missing docs
      4. init_tracing() (M5, no-op for now)
      5. MCPRegistry().startup() (M3, no-op for now)
      6. build_graph() once and stash on app.state — compiling per request would
         re-spawn subprocesses and thrash

    Shutdown:
      - registry.shutdown() -> sandbox.shutdown_all() (M3)
      - nothing else to clean up: WebSocket handlers close their own sockets
    """
    from dotenv import load_dotenv

    from backend.graph.supervisor import build_graph

    load_dotenv()

    config = get_config()
    for warning in startup_checks(config):
        logger.warning(warning)

    app.state.graph = build_graph()
    app.state.connections = ConnectionManager()

    yield


app = FastAPI(title="Chain of Command", lifespan=lifespan)

_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- HTTP -----------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, bool]:
    """Ollama reachable, config loaded. Qdrant/MCP liveness land in M2/M3."""
    status = {"config_loaded": False, "ollama": False}
    try:
        get_config()
        status["config_loaded"] = True
    except Exception:  # noqa: BLE001, S110 - health check must never raise
        logger.debug("health check: config not loaded", exc_info=True)
    try:
        import ollama as ollama_client

        ollama_client.list()
        status["ollama"] = True
    except Exception:  # noqa: BLE001, S110 - health check must never raise
        logger.debug("health check: ollama unreachable", exc_info=True)
    return status


@app.get("/api/config")
async def public_config() -> dict[str, Any]:
    """Personas and themes for the frontend. ⚠ Public — never include MCP
    commands, admin emails, scheduling links, or anything else private."""
    config = get_config()
    return {
        "company_name": config.company.name,
        "personas": {
            tier.value: {
                "name": config.personas.get(tier).name,
                "title": config.personas.get(tier).title,
                "theme": config.personas.get(tier).theme,
            }
            for tier in (Tier.FRONT_DESK, Tier.MANAGER, Tier.VICE_PRESIDENT, Tier.CEO)
        },
    }


# TODO(M5): GET /api/analytics — see backend/observability/tracing.py.


# --- WebSocket ------------------------------------------------------------


async def _send(websocket: WebSocket, payload: dict | Any) -> None:
    data = payload if isinstance(payload, dict) else payload.model_dump()
    await websocket.send_json(data)


async def _resend_pending_interrupt(websocket: WebSocket, snapshot: Any) -> None:
    if snapshot.interrupts:
        await _send(websocket, snapshot.interrupts[0].value)


async def _stream_turn(
    websocket: WebSocket, graph: Any, thread_config: dict, stream_input: Any
) -> None:
    """Drive one turn of the graph, mapping node output onto the wire protocol.

    Token-by-token streaming is limited to the "agent" node's chat model —
    that is the only LLM call in a tier loop meant to be read live by the
    customer. classify/verdict/summarize are structured-output calls on the
    same models; streaming their raw JSON would leak internals onto the chat.
    """
    async for event in graph.astream_events(stream_input, thread_config, version="v2"):
        kind = event["event"]
        node = (event.get("metadata") or {}).get("langgraph_node")
        # A node's own on_chain_end has event["name"] == its node name; nested
        # runnables inside it (e.g. the ChatOllama call in do_handoff) share the
        # same langgraph_node metadata but a different event name — filtering on
        # both is what isolates the node's OWN output from its internals.
        is_node_boundary = kind == "on_chain_end" and event.get("name") == node

        if kind == "on_chat_model_stream" and node == "agent":
            chunk = event["data"]["chunk"]
            content = getattr(chunk, "content", "")
            if content:
                await _send(websocket, TokenEvent(content=content))

        elif is_node_boundary and node == "introduce":
            output = event["data"].get("output") or {}
            messages = output.get("messages") or []
            snapshot = await graph.aget_state(thread_config)
            tier = snapshot.values.get("current_tier")
            if tier is not None:
                persona = get_config().personas.get(tier)
                from backend.api.events import AgentIntroEvent

                await _send(
                    websocket,
                    AgentIntroEvent(
                        tier=tier, persona_name=persona.name, persona_title=persona.title
                    ),
                )
            for m in messages:
                text = getattr(m, "content", "")
                if text:
                    await _send(websocket, TokenEvent(content=text))

        elif is_node_boundary and node == "handoff":
            output = event["data"].get("output") or {}
            tier_change = output.get("_last_tier_change")
            if tier_change:
                await _send(websocket, tier_change)

        elif is_node_boundary and node == "human":
            output = event["data"].get("output") or {}
            for m in output.get("messages") or []:
                text = getattr(m, "content", "")
                if text:
                    await _send(websocket, TokenEvent(content=text))
            from backend.api.events import HumanEscalationEvent

            admin = get_config().escalation.human_admin
            await _send(
                websocket,
                HumanEscalationEvent(
                    channels=output.get("_last_human_escalation_channels") or [],
                    scheduling_link=str(admin.scheduling_link) if admin.scheduling_link else None,
                    message="A member of our team has been notified and will follow up personally.",
                ),
            )

    from backend.api.events import TurnEndEvent

    await _send(websocket, TurnEndEvent())

    snapshot = await graph.aget_state(thread_config)
    await _resend_pending_interrupt(websocket, snapshot)


@app.websocket("/ws/chat/{session_id}")
async def chat(websocket: WebSocket, session_id: str) -> None:
    """The main chat channel.

    Flow:
      1. accept()
      2. Resume from checkpoint if `session_id` is known; otherwise start fresh
         on the first user_message.
         ⚠ On resume, if the graph is paused at an interrupt, RE-SEND the pending
           escalation_prompt / context_request. Otherwise a customer who
           refreshed sees a dead chat waiting on an answer to a question the UI
           no longer shows.
      3. Loop: receive a client event, dispatch:
           user_message        -> astream_events through the graph
           escalation_response -> Command(resume=approved)
           context_response    -> Command(resume=answer)
      4. Map graph events onto the wire protocol in backend/api/events.py.

    On disconnect, graph state is NOT torn down — the checkpoint is the
    session; a dropped socket is not the end of a conversation.

    TODO(M5): auth. Sessions are currently anonymous and a session_id is
      guessable, so anyone with the id can read the conversation. Must be closed
      before any real deployment — see PLAN.md "Open items".
    """
    from langchain_core.messages import HumanMessage
    from langgraph.types import Command

    from backend.graph.state import new_state

    await websocket.accept()
    graph = websocket.app.state.graph
    connections: ConnectionManager = websocket.app.state.connections
    connections.register(session_id, websocket)
    thread_config = {"configurable": {"thread_id": session_id}}

    try:
        snapshot = await graph.aget_state(thread_config)
        is_new_session = not snapshot.values
        if not is_new_session:
            await _resend_pending_interrupt(websocket, snapshot)

        while True:
            raw = await websocket.receive_json()
            event = parse_client_event(raw)

            if event is None:
                await _send(
                    websocket,
                    ErrorEvent(message="Sorry, I didn't understand that.", recoverable=True),
                )
                continue

            try:
                if isinstance(event, UserMessage):
                    if is_new_session:
                        stream_input: Any = new_state(session_id)
                        stream_input["messages"] = [HumanMessage(content=event.content)]
                        is_new_session = False
                    else:
                        stream_input = {"messages": [HumanMessage(content=event.content)]}
                elif isinstance(event, EscalationResponse):
                    stream_input = Command(resume=event.approved)
                elif isinstance(event, ContextResponse):
                    stream_input = Command(resume=event.answer)
                else:
                    continue

                await _stream_turn(websocket, graph, thread_config, stream_input)
            except WebSocketDisconnect:
                # The client dropped mid-turn (network blip, tab closed). There
                # is no socket left to report anything to — propagate to the
                # outer handler rather than trying to send an ErrorEvent into
                # a connection that no longer exists.
                raise
            except Exception:
                logger.exception("Error processing turn for session %s", session_id)
                try:
                    await _send(
                        websocket,
                        ErrorEvent(
                            message="Something went wrong on our end — please try again.",
                            recoverable=True,
                        ),
                    )
                except Exception:  # noqa: BLE001, S110 - best-effort report; a
                    # dead socket can fail here as WebSocketDisconnect OR a
                    # plain RuntimeError ("Cannot call send once a close
                    # message has been sent") depending on exactly when it
                    # died. Either way there's nothing left to report to —
                    # swallow it and let the next receive_json() surface the
                    # real WebSocketDisconnect to the outer handler.
                    logger.debug("Could not report error to a disconnected client", exc_info=True)
    except WebSocketDisconnect:
        pass
    finally:
        connections.unregister(session_id, websocket)
