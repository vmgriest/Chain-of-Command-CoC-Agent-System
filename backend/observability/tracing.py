"""Tracing and escalation analytics.  (M5)

⚠ ONE TRACE PER TICKET. Each tier is a child span under a single ticket-level
  root. Per-tier traces would show four disconnected conversations and hide the
  thing actually worth seeing.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.config.schema import Tier
    from backend.graph.state import CoCState

logger = logging.getLogger("coc.observability")

# LangSmith over OTel: LangGraph-native (astream_events already carries
# `langgraph_node` metadata LangSmith understands directly) and this project
# already depends on langchain/langgraph — no second tracing stack to run.


def init_tracing() -> None:
    """Configure LangSmith from LANGSMITH_* env vars. No-op when tracing is
    off — the system must run identically without it.

    LangSmith auto-instruments every LangChain/LangGraph call once the
    LANGCHAIN_* env vars are set; there is no SDK client to construct here.
    """
    if os.environ.get("LANGSMITH_TRACING", "false").lower() != "true":
        return
    if not os.environ.get("LANGSMITH_API_KEY"):
        logger.warning(
            "LANGSMITH_TRACING=true but LANGSMITH_API_KEY is not set — tracing stays off."
        )
        return

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = os.environ["LANGSMITH_API_KEY"]
    os.environ["LANGCHAIN_PROJECT"] = os.environ.get("LANGSMITH_PROJECT", "chain-of-command")
    logger.info("LangSmith tracing enabled for project %r", os.environ["LANGCHAIN_PROJECT"])


# TODO(M5): span attributes to set on every tier span:
#     ticket_id, session_id, tier, persona_name, model_id,
#     tool_calls[], attempt_count, escalation_reason,
#     handoff_packet_tokens, guardrail_hits[]
#
#   handoff_packet_tokens is the one to watch: if it creeps upward over a
#   session, the summarizer is accumulating rather than summarizing and the
#   protocol is quietly failing.


# --- analytics ------------------------------------------------------------


@dataclass
class TicketMetrics:
    """Per-ticket outcome. Aggregated, these justify the whole tiering design —
    if most tickets end at the Front Desk, the architecture is paying off."""

    ticket_id: str
    resolved_at_tier: Tier | None  # None when it reached a human
    tiers_traversed: int
    total_turns: int
    duration_seconds: float
    escalation_reasons: list[str]
    human_escalated: bool
    user_initiated_escalations: int
    agent_initiated_escalations: int
    consent_refusals: int


# One JSON file, keyed by ticket_id, upserted after every turn — a "closed
# ticket" isn't a concept the system has (there is no explicit end-of-session
# signal in a live chat), so this tracks the CURRENT state of every ticket
# rather than a final snapshot taken once. Reading it always reflects "as of
# the last turn," which for a support-volume analytics view is what matters
# anyway. Same "JSON file is fine for now" convention used elsewhere in this
# codebase for small local state that doesn't need a real database yet.
ANALYTICS_PATH = Path(os.environ.get("ANALYTICS_PATH", ".analytics.json"))


def _load_tickets() -> dict[str, dict]:
    if not ANALYTICS_PATH.exists():
        return {}
    try:
        return json.loads(ANALYTICS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Analytics store at %s is corrupt; treating as empty", ANALYTICS_PATH)
        return {}


def _save_tickets(data: dict[str, dict]) -> None:
    ANALYTICS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_ticket(metrics: TicketMetrics) -> None:
    """Upsert one ticket's current metrics by ticket_id."""
    data = _load_tickets()
    row = asdict(metrics)
    row["resolved_at_tier"] = metrics.resolved_at_tier.value if metrics.resolved_at_tier else None
    data[metrics.ticket_id] = row
    _save_tickets(data)


def metrics_from_state(state: CoCState) -> TicketMetrics:
    """Build a TicketMetrics snapshot from live graph state.

    `resolved_at_tier` is set to the current tier whenever the ticket hasn't
    reached a human — "resolved" here means "not (yet) escalated past every
    tier," the only signal this system has without an explicit close event.
    """
    import time

    from backend.config.schema import ORDER

    tier: Tier = state["current_tier"]
    human_escalated = bool(state.get("human_notified"))

    return TicketMetrics(
        ticket_id=state["ticket_id"],
        resolved_at_tier=None if human_escalated else tier,
        tiers_traversed=ORDER.index(tier) + 1,
        total_turns=state.get("turn_count", 0),
        duration_seconds=time.time() - state.get("started_at", time.time()),
        escalation_reasons=list(state.get("escalation_reasons", [])),
        human_escalated=human_escalated,
        user_initiated_escalations=state.get("user_initiated_escalations", 0),
        agent_initiated_escalations=state.get("agent_initiated_escalations", 0),
        consent_refusals=state.get("consent_refusals", 0),
    )


def record_ticket_snapshot(state: CoCState) -> None:
    """Called once per turn from backend/api/main.py after streaming
    completes — never on the hot path of a token, and never able to break a
    conversation (see the try/except at the call site)."""
    record_ticket(metrics_from_state(state))


def aggregate_stats() -> dict:
    """Aggregate stats worth surfacing — the payoff metric for the whole
    tiering argument. Exposed at GET /api/analytics (backend/api/main.py).

      - resolution rate per tier (the headline number)
      - escalation rate, split user- vs agent-initiated
      - consent refusal rate — high refusal means escalation is being offered
        badly, or offered too eagerly
      - mean tiers traversed per ticket
      - mean time in-session per ticket
      - human escalation rate
      - most common escalation_reason strings — this is the backlog for what
        to build next, straight from production
    """
    from collections import Counter

    tickets = list(_load_tickets().values())
    n = len(tickets)
    if n == 0:
        return {"ticket_count": 0}

    resolved_by_tier = Counter(t["resolved_at_tier"] for t in tickets if t["resolved_at_tier"])
    human_escalated = sum(1 for t in tickets if t["human_escalated"])
    total_user_initiated = sum(t["user_initiated_escalations"] for t in tickets)
    total_agent_initiated = sum(t["agent_initiated_escalations"] for t in tickets)
    total_refusals = sum(t["consent_refusals"] for t in tickets)

    reasons: Counter[str] = Counter()
    for t in tickets:
        reasons.update(t["escalation_reasons"])

    return {
        "ticket_count": n,
        "resolution_rate_per_tier": {tier: count / n for tier, count in resolved_by_tier.items()},
        "human_escalation_rate": human_escalated / n,
        "user_initiated_escalations": total_user_initiated,
        "agent_initiated_escalations": total_agent_initiated,
        # Only agent-initiated escalation goes through the consent gate — a
        # user-initiated one always skips it — so that's the right denominator.
        "consent_refusal_rate": (total_refusals / total_agent_initiated)
        if total_agent_initiated
        else 0.0,
        "mean_tiers_traversed": sum(t["tiers_traversed"] for t in tickets) / n,
        "mean_duration_seconds": sum(t["duration_seconds"] for t in tickets) / n,
        "top_escalation_reasons": reasons.most_common(10),
    }
