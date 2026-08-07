"""Tracing and escalation analytics.  (M5)

⚠ ONE TRACE PER TICKET. Each tier is a child span under a single ticket-level
  root. Per-tier traces would show four disconnected conversations and hide the
  thing actually worth seeing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.config.schema import Tier

# TODO(M5): pick LangSmith (easier, LangGraph-native) or OTel (vendor-neutral,
#   fits existing infra). LangSmith unless there is a reason not to.


def init_tracing() -> None:
    """TODO(M5): configure from LANGSMITH_* env vars. No-op when tracing is off —
    tracing must be optional, and the system must run identically without it."""
    raise NotImplementedError


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


# TODO(M5): record_ticket(metrics) -> None

# TODO(M5): aggregate stats worth surfacing:
#     - resolution rate per tier (the headline number)
#     - escalation rate, split user- vs agent-initiated
#     - consent refusal rate — high refusal means escalation is being offered
#       badly, or offered too eagerly
#     - mean tiers traversed per ticket
#     - time to resolution per tier
#     - human escalation rate
#     - most common escalation_reason strings — this is the backlog for what to
#       build next, straight from production

# TODO(M5): expose at GET /api/analytics, plus a simple admin view.
