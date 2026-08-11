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


@asynccontextmanager  # everything before `yield` runs once at process startup,
# everything after it runs once at shutdown — FastAPI calls this exactly once
# and keeps the app alive for the whole `yield`.
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown.

    Startup:
      1. load_dotenv()
      2. get_config()  — fail fast and loudly on a bad config
      3. startup_checks() — warn about unpulled models, missing docs
      4. init_tracing() (M5)
      5. MCPRegistry().startup(), then set_registry() — tier builds below read
         it via get_registry()
      6. build_graph() once and stash on app.state — compiling per request would
         re-spawn subprocesses and thrash

    Shutdown:
      - registry.shutdown() -> sandbox.shutdown_all()
      - nothing else to clean up: WebSocket handlers close their own sockets
    """
    from dotenv import load_dotenv

    from backend.graph.supervisor import build_graph
    from backend.mcp.registry import MCPRegistry, set_registry
    from backend.observability.tracing import init_tracing

    load_dotenv()

    config = get_config()
    for warning in startup_checks(config):
        logger.warning(warning)

    init_tracing()

    registry = MCPRegistry(config)
    await registry.startup()
    set_registry(registry)
    for server_name, healthy in registry.health().items():
        if not healthy:
            logger.warning("MCP server %r failed to start — continuing without it", server_name)

    app.state.registry = registry
    app.state.graph = build_graph()
    app.state.connections = ConnectionManager()

    yield

    await registry.shutdown()


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
async def health() -> dict[str, bool | dict[str, bool]]:
    """Ollama reachable, config loaded, Qdrant collection populated, MCP
    servers connected. "RAG is configured but the collection is empty" is a
    common and confusing failure otherwise — surfacing it here catches it
    before a customer does."""
    status: dict[str, bool | dict[str, bool]] = {
        "config_loaded": False,
        "ollama": False,
        "rag": False,
    }
    try:
        config = get_config()
        status["config_loaded"] = True
    except Exception:  # noqa: BLE001, S110 - health check must never raise
        logger.debug("health check: config not loaded", exc_info=True)
        return status

    try:
        import ollama as ollama_client

        ollama_client.list()
        status["ollama"] = True
    except Exception:  # noqa: BLE001, S110 - health check must never raise
        logger.debug("health check: ollama unreachable", exc_info=True)

    try:
        from backend.rag.retriever import health as rag_health

        status["rag"] = await rag_health(config.knowledge.qdrant_collection)
    except Exception:  # noqa: BLE001, S110 - health check must never raise
        logger.debug("health check: qdrant unreachable", exc_info=True)

    try:
        from backend.mcp.registry import get_registry

        status["mcp_servers"] = get_registry().health()
    except Exception:  # noqa: BLE001, S110 - health check must never raise
        logger.debug("health check: mcp registry unavailable", exc_info=True)

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


@app.get("/api/analytics")
async def analytics() -> dict[str, Any]:
    """Aggregate escalation analytics — see backend/observability/tracing.py.

    ⚠ No auth (same open question as the WS session — see README.md's
    "Still open" list). Fine for local/demo use; close this before any real
    deployment.
    """
    from backend.observability.tracing import aggregate_stats

    return aggregate_stats()


@app.post("/api/admin/reload-config")
async def reload_config_endpoint() -> dict[str, Any]:
    """Re-read company_config.json without restarting.

    Picks up content changes (knowledge sources, escalation policy, contact
    channels) on the next tool call / turn. Model ids and personas need a full
    restart to take effect — see reload_config()'s docstring in
    backend/config/loader.py for why.

    ⚠ No auth — same open item as /api/analytics and the WS session.
    """
    from backend.config.loader import ConfigError, reload_config

    try:
        config = reload_config()
    except ConfigError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "company_name": config.company.name}


# --- WebSocket ------------------------------------------------------------


async def _send(websocket: WebSocket, payload: dict | Any) -> None:
    data = payload if isinstance(payload, dict) else payload.model_dump()
    await websocket.send_json(data)


async def _resend_pending_interrupt(websocket: WebSocket, snapshot: Any) -> None:
    if snapshot.interrupts:
        await _send(websocket, snapshot.interrupts[0].value)


async def _greet_new_session(websocket: WebSocket, graph: Any, thread_config: dict) -> None:
    """Penny (or whoever's configured at Front Desk) introduces herself the
    moment a brand-new session connects — BEFORE the customer types anything
    — the same way a tier introduces itself immediately on a handoff, with no
    new user message required. Without this, Front Desk was the only tier
    that never got a proactive greeting: its self-introduction only fired as
    a side effect of the customer's first message, via
    backend/graph/tiers/base.py's own "introduce" node, so the greeting and
    the answer to their first question arrived glued together in one turn.

    Reuses `introduce()` — the exact function every handoff already uses —
    rather than duplicating greeting logic, so Front Desk's first words and a
    post-handoff persona's first words are generated the same way.

    Seeds the checkpoint via aupdate_state() before any node has run, which
    LangGraph supports for pre-populating a fresh thread's state. The
    customer's actual first message is then just a normal
    `{"messages": [...]}` update on top of already-initialized state — not
    a special "first turn" case anymore.
    """
    from langgraph.constants import START

    from backend.api.events import AgentIntroEvent, TurnEndEvent
    from backend.config.schema import Tier
    from backend.graph.state import new_state
    from backend.graph.tiers.base import introduce

    session_id = thread_config["configurable"]["thread_id"]
    initial_state = new_state(session_id)
    await graph.aupdate_state(thread_config, initial_state, as_node=START)

    persona = get_config().personas.front_desk
    intro_updates = await introduce(initial_state, persona)
    await graph.aupdate_state(thread_config, intro_updates, as_node="introduce")

    await _send(
        websocket,
        AgentIntroEvent(
            tier=Tier.FRONT_DESK, persona_name=persona.name, persona_title=persona.title
        ),
    )
    for m in intro_updates["messages"]:
        text = getattr(m, "content", "")
        if text:
            await _send(websocket, TokenEvent(content=text))
    await _send(websocket, TurnEndEvent())


async def _stream_turn(
    websocket: WebSocket, graph: Any, thread_config: dict, stream_input: Any
) -> None:
    """Drive one turn of the graph, mapping node output onto the wire protocol.

    Token-by-token streaming is limited to the "agent" node's chat model —
    that is the only LLM call in a tier loop meant to be read live by the
    customer. classify/verdict/summarize are structured-output calls on the
    same models; streaming their raw JSON would leak internals onto the chat.
    The CEO tier's evaluator-optimizer loop (backend/graph/tiers/ceo.py) runs
    its evaluate/revise calls INSIDE that same "agent" node, so metadata alone
    can't tell them apart from the tier's real response — those calls are
    tagged "coc_internal" and excluded here on that basis instead.
    """
    snapshot_before = await graph.aget_state(thread_config)
    was_human_notified = bool(snapshot_before.values.get("human_notified"))

    async for event in graph.astream_events(stream_input, thread_config, version="v2"):
        kind = event["event"]
        node = (event.get("metadata") or {}).get("langgraph_node")
        # A node's own on_chain_end has event["name"] == its node name; nested
        # runnables inside it (e.g. the ChatOllama call in do_handoff) share the
        # same langgraph_node metadata but a different event name — filtering on
        # both is what isolates the node's OWN output from its internals.
        is_node_boundary = kind == "on_chain_end" and event.get("name") == node

        if kind == "on_chat_model_stream" and node == "agent":
            if "coc_internal" in (event.get("tags") or []):
                continue
            chunk = event["data"]["chunk"]
            content = getattr(chunk, "content", "")
            if content:
                await _send(websocket, TokenEvent(content=content))

        elif is_node_boundary and node == "introduce":
            # "introduce" is every tier subgraph's entry point, so this
            # boundary fires on EVERY turn, not just a fresh handoff —
            # introduce_node itself only produces messages when
            # tier_just_changed was true (see backend/graph/tiers/base.py).
            # Found live: sending AgentIntroEvent unconditionally here made
            # the frontend open a SECOND agent bubble via startAgentMessage()
            # on every ordinary follow-up turn, on top of the one
            # MessageInput.tsx already opens optimistically on send — the
            # first bubble then never receives tokens or a finishAgentMessage()
            # call, and is stuck rendering an empty, permanently "streaming"
            # bubble. Gating on `messages` being non-empty is what ties this
            # event to an ACTUAL introduction rather than every turn.
            output = event["data"].get("output") or {}
            messages = output.get("messages") or []
            if messages:
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
            # The supervisor-routed path's own customer-facing message (see
            # backend/graph/supervisor.py::human_escalation_node). The
            # HumanEscalationEvent itself is emitted once below, from a state
            # diff — that also covers the CEO's own escalate_to_human TOOL
            # path, which has no "human" node at all.
            output = event["data"].get("output") or {}
            for m in output.get("messages") or []:
                text = getattr(m, "content", "")
                if text:
                    await _send(websocket, TokenEvent(content=text))

    from backend.api.events import TurnEndEvent

    await _send(websocket, TurnEndEvent())

    snapshot = await graph.aget_state(thread_config)

    try:
        from backend.observability.tracing import record_ticket_snapshot

        record_ticket_snapshot(snapshot.values)
    except Exception:  # noqa: BLE001, S110 - analytics must never break the chat
        logger.debug("Failed to record analytics snapshot", exc_info=True)

    if not was_human_notified and snapshot.values.get("human_notified"):
        from backend.api.events import HumanEscalationEvent
        from backend.notifications.scheduling import build_scheduling_offer

        admin = get_config().escalation.human_admin
        scheduling_link = None
        if admin.scheduling_link:
            packet = snapshot.values.get("packet")
            offer = build_scheduling_offer(packet, str(admin.scheduling_link))
            scheduling_link = offer["link"]

        await _send(
            websocket,
            HumanEscalationEvent(
                channels=snapshot.values.get("_last_human_escalation_channels") or [],
                scheduling_link=scheduling_link,
                message="A member of our team has been notified and will follow up personally.",
            ),
        )

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

    TODO: auth. Sessions are currently anonymous and a session_id is
      guessable, so anyone with the id can read the conversation. Must be closed
      before any real deployment — see README.md's "Still open" list.
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
        if is_new_session:
            await _greet_new_session(websocket, graph, thread_config)
            is_new_session = False
        else:
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
