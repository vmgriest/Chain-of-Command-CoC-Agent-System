"""Shared tier loop factory.  ⭐ WRITE THIS SECOND (right after handoff.py).

Every tier is this loop with different bindings. Writing the factory before any
individual tier is what stops the four tiers drifting into four bespoke
implementations that have to be maintained separately.

Each tier runs its own agentic loop:

    receive -> (introduce if just escalated) -> reason -> [call tools] ->
    [ask user for context if needed] -> respond OR request escalation
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from backend.config.schema import Persona, Tier

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

    from backend.graph.state import CoCState


class TierVerdict(BaseModel):
    """Structured output every tier produces alongside its reply.

    This is how a tier signals it is stuck without escalating itself — the
    supervisor reads the verdict and decides.
    """

    can_resolve: bool = Field(
        description="True if this tier fully answered the question with what it has. "
        "False if it lacks the knowledge, tools, or access to finish."
    )
    escalation_reason: str | None = Field(
        default=None,
        description="When can_resolve is False: the specific missing capability. "
        "Name the gap ('no access to billing records'), not a feeling.",
    )
    needs_context: str | None = Field(
        default=None,
        description="A question to ask the user before continuing (account number, "
        "order id, ...). Null when nothing is needed — the loop then runs "
        "uninterrupted. Do NOT ask just to confirm you understood.",
    )


# TODO(M1): BASE_SYSTEM_PROMPT template. Rendered per tier with:
#     persona.name, persona.title, company.name, company.support_scope,
#     the incoming HandoffPacket, and the tier's capability description.
#
#   Must cover:
#     - Introduce yourself by name and title on the first turn after escalation.
#     - You have been handed a packet. Do not ask the customer to repeat
#       anything already in verified_facts.
#     - Do not re-attempt anything in ruled_out.
#     - Be honest about limits. Saying "I can't do this from here" and offering
#       to escalate is a good outcome, not a failure.
#     - Never promise something you cannot deliver.


def build_tier(
    tier: Tier,
    persona: Persona,
    model_id: str,
    tools: list[BaseTool],
    capability_description: str,
) -> CompiledStateGraph:
    """TODO(M1): build one tier's compiled subgraph.

    Nodes:
      introduce  — only when state["tier_just_changed"]; streams the self-intro,
                   then clears the flag.
      agent      — the model call. Tools bound ONLY if `tools` is non-empty.
      tools      — ToolNode. NOT ADDED AT ALL when `tools` is empty.
      verdict    — structured TierVerdict; sets pending_escalation when stuck.

    Edges: introduce -> agent -> (tools -> agent)* -> verdict -> END

    ⚠ INVARIANT: when `tools` is empty, this must build a graph with NO tool node
      and NO tools bound to the model. Not a filtered registry — an absent one.
      The Front Desk must have no runtime path to a tool call, so that no prompt
      can talk it into one. There is a test for this; keep it passing.

    TODO(M1): increment attempt_count when the verdict says can_resolve is False.
    TODO(M3): the VP tier needs concurrent tool execution — asyncio.gather over
      independent calls rather than sequential ToolNode dispatch. Add it here
      behind a flag so all tiers benefit, rather than forking vice_president.py.
    """
    raise NotImplementedError


def make_model(model_id: str, tools: list[BaseTool]):  # noqa: ANN201
    """TODO(M1): ChatOllama bound to `tools`.

    If `tools` is empty, return the model UNBOUND — do not call .bind_tools([]).
    Some providers treat an empty tool list differently from no tool list at all,
    and the whole Front Desk guarantee rests on this distinction.
    """
    raise NotImplementedError


async def introduce(state: CoCState, persona: Persona) -> dict:
    """TODO(M1): the self-introduction, emitted on every tier change.

    Should acknowledge the handoff, not restart the conversation — the customer
    has already explained themselves once. Reference the packet's customer_intent
    so the introduction demonstrates the handoff worked.
    """
    raise NotImplementedError
