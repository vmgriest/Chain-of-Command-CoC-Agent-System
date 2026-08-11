"""Tier 4 — CEO.  ALL TOOLS + HUMAN ESCALATION.

The last stop. Re-attempts the problem from scratch with the full toolset before
reaching for a person.

Capabilities: evaluator-optimizer, human-in-the-loop, observability, output guardrails.

Two behaviors that are easy to get wrong:

  1. THE SESSION DOES NOT END. When the CEO emails an admin or books a call, the
     chat stays live. The customer is told what happened and what to expect, and
     can keep talking.

  2. NO AUTO-DESCALATION. A simple follow-up at this tier ("what's your refund
     window?") is just answered here. The customer is never bounced back down.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field

from backend.config.loader import get_config
from backend.config.schema import Tier
from backend.graph.state import CoCState  # noqa: TC001 - see the note in tiers/base.py:

# @tool-decorated functions get their schema from get_type_hints() against this
# module's globals, which needs CoCState (and everything else in escalate_to_human's
# signature below) resolvable at runtime, not just for type checkers — same
# reasoning as the LangGraph routing-function case in base.py, but triggered by
# pydantic's schema inference on a @tool function instead of add_conditional_edges.
from backend.graph.tiers.base import build_tier

if TYPE_CHECKING:
    from langchain_core.messages import AIMessage, BaseMessage
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger("coc.tiers.ceo")

CAPABILITY_DESCRIPTION = """\
You have every tool available in this organization. You are the final escalation
point, so exhaust your own options before involving a human. If you do involve
one, tell the customer exactly what you did and what happens next — and keep
helping them in the meantime.
"""

# --- evaluator-optimizer ---------------------------------------------------

MAX_OPTIMIZE_ITERATIONS = 3
MAX_OPTIMIZE_TOKENS = 8000


class DraftEvaluation(BaseModel):
    """Explicit pass/fail criteria, not a vibe check.

    The evaluator is a SEPARATE model call from the drafter. Asking one call to
    both write and grade its own answer produces agreeable nonsense.
    """

    addresses_intent: bool = Field(description="Does this answer what the customer actually wants?")
    factually_grounded: bool = Field(
        description="Is every claim backed by a tool result or document?"
    )
    no_unbacked_promises: bool = Field(
        description="Does it avoid committing the company to anything unverified?"
    )
    actionable: bool = Field(description="Can the customer act on this, or is it vague?")
    critique: str = Field(description="What specifically to fix. Empty when all checks pass.")

    @property
    def passed(self) -> bool:
        return (
            self.addresses_intent
            and self.factually_grounded
            and self.no_unbacked_promises
            and self.actionable
        )


EVALUATION_PROMPT = """\
You are grading a customer support reply before it is sent, on behalf of {persona_name}.

Customer's underlying goal: {customer_intent}

Draft reply:
{draft}

Score the draft honestly against all four criteria. If any fails, explain \
specifically what to fix in `critique` — the drafter will revise from your \
critique alone, without seeing this conversation again.
"""

REVISION_PROMPT = """\
Your previous draft:
{draft}

An evaluator found a problem: {critique}

Revise the draft to address this critique. Reply with ONLY the revised \
customer-facing message — no preamble, no explanation of what changed.
"""


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), same convention as
    HandoffPacket.estimated_tokens() in backend/graph/handoff.py."""
    return max(1, len(text) // 4)


def make_response_optimizer(model_id: str, persona_name: str):  # noqa: ANN201
    """draft -> evaluate -> revise, bounded by MAX_OPTIMIZE_ITERATIONS *and*
    MAX_OPTIMIZE_TOKENS. Returns the best draft on exhaustion, never an error —
    the customer gets an imperfect answer rather than a failure.

    Returned as a closure (rather than a free function taking model_id every
    call) so build_tier() can pass it straight in as `response_optimizer`.
    """
    from langchain_core.messages import HumanMessage

    from backend.graph.tiers.base import make_model

    async def optimize(
        _state: CoCState, messages: list[BaseMessage], draft: AIMessage
    ) -> AIMessage:
        evaluator_model = make_model(model_id, [], temperature=0).with_structured_output(
            DraftEvaluation
        )
        reviser_model = make_model(model_id, [], temperature=0.3)

        customer_intent = _state["packet"].customer_intent or "(not established)"
        current = draft
        tokens_used = _estimate_tokens(str(current.content))

        # Tagged "coc_internal" so backend/api/main.py's token streamer can tell
        # these nested calls apart from the tier's main "agent" response — both
        # run inside the same "agent" graph node, so `langgraph_node` metadata
        # alone can't distinguish them. Untagged calls (the initial draft, and
        # any tier without an optimizer) stream normally.
        internal_config = {"tags": ["coc_internal"]}

        for iteration in range(MAX_OPTIMIZE_ITERATIONS):
            evaluation: DraftEvaluation = await evaluator_model.ainvoke(
                EVALUATION_PROMPT.format(
                    persona_name=persona_name,
                    customer_intent=customer_intent,
                    draft=current.content,
                ),
                config=internal_config,
            )
            logger.info(
                "CEO evaluator-optimizer iteration %d for ticket %s: passed=%s critique=%r",
                iteration,
                _state.get("ticket_id"),
                evaluation.passed,
                evaluation.critique,
            )
            if evaluation.passed:
                break
            if tokens_used >= MAX_OPTIMIZE_TOKENS:
                logger.warning(
                    "CEO evaluator-optimizer hit MAX_OPTIMIZE_TOKENS for ticket %s; "
                    "returning best draft so far rather than looping further.",
                    _state.get("ticket_id"),
                )
                break

            revision_request = REVISION_PROMPT.format(
                draft=current.content, critique=evaluation.critique
            )
            revised = await reviser_model.ainvoke(
                [*messages, current, HumanMessage(content=revision_request)],
                config=internal_config,
            )
            tokens_used += _estimate_tokens(str(revised.content))
            current = revised

        # Output guardrail: the LAST check before this reaches the customer,
        # separate from DraftEvaluation above (which grades usefulness, not
        # safety). On failure, one more revision from the guardrail's own
        # critique — never a hard block. A refusal helps nobody when a better
        # answer is one revision away, and this is the last tier there is.
        from backend.graph.middleware.guardrails import check_output

        output_verdict = await check_output(_state, str(current.content))
        if not output_verdict.passed:
            logger.warning(
                "CEO output guardrail flagged ticket %s: %s",
                _state.get("ticket_id"),
                output_verdict.reason,
            )
            revision_request = REVISION_PROMPT.format(
                draft=current.content, critique=output_verdict.reason
            )
            current = await reviser_model.ainvoke(
                [*messages, current, HumanMessage(content=revision_request)],
                config=internal_config,
            )

        return current

    return optimize


def build(model_id: str) -> CompiledStateGraph:
    """build_tier(Tier.CEO, ..., tools=real_tools(), response_optimizer=...)"""
    persona = get_config().personas.ceo
    return build_tier(
        Tier.CEO,
        persona,
        model_id,
        real_tools(),
        CAPABILITY_DESCRIPTION,
        response_optimizer=make_response_optimizer(model_id, persona.name),
    )


def make_escalate_to_human_tool():  # noqa: ANN201
    """escalate_to_human(reason, urgency) — the CEO's own tool for looping in a
    human PROACTIVELY, mid-conversation, rather than waiting for its own
    TierVerdict to give up first (that automatic path already exists via
    backend/graph/supervisor.py::human_escalation_node — this tool is for
    cases the CEO recognizes immediately: executive judgment, a PR-sensitive
    situation, or something already exhausted at every lower tier).

    Returns a Command so the tool call itself updates graph state directly —
    human_notified / _last_human_escalation_channels — giving this path exact
    parity with the supervisor-routed one. backend/api/main.py detects either
    path the same way: a state diff on human_notified between turn start and
    turn end, not a specific node name.

    Fans out to backend/notifications/: email, scheduling link. Attaches
    the HandoffPacket so the admin has full context without reading the
    transcript — same protocol, different consumer.

    Sets state["human_notified"] = True and RETURNS TO THE CONVERSATION —
    the tool result becomes a ToolMessage, and the CEO's next turn continues
    normally. Must not end the session.
    """
    from langchain_core.tools import tool

    @tool
    async def escalate_to_human(
        reason: str,
        urgency: Literal["normal", "urgent"],
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[CoCState, InjectedState],
    ) -> Command:
        """Loop in a human admin when the issue needs a person: executive
        judgment, a PR-sensitive situation, or something that has already
        failed at every lower tier. The conversation continues after this —
        you keep helping the customer while a human follows up separately."""
        from backend.notifications import notify_human, session_url

        packet = state["packet"]
        url = session_url(state["session_id"])
        channels = await notify_human(packet, reason, urgency, url)

        result = (
            f"Notified the team via {', '.join(channels)}."
            if channels
            else "No notification channel is configured — tell the customer this "
            "could not be escalated to a person right now."
        )
        return Command(
            update={
                "human_notified": True,
                "_last_human_escalation_channels": channels,
                "messages": [ToolMessage(content=result, tool_call_id=tool_call_id)],
            }
        )

    return escalate_to_human


def real_tools() -> list[BaseTool]:
    """Everything the VP has, plus any CEO-only MCP tools, plus
    escalate_to_human.

    ⚠ A server can list BOTH `vice_president` and `ceo` in its `tiers` array
      (ours does — see company_config.json's `internal_tools`), which means
      `registry.tools_for_tier(CEO)` and `registry.tools_for_tier(VICE_PRESIDENT)`
      legitimately overlap. Naively concatenating vp_real_tools() (which
      already pulled the VP-scoped copy) with the CEO-scoped copy DUPLICATES
      every shared tool — caught live: `internal_tools.rag_search` etc.
      appeared twice in CEO's bound tool list. Filtered here by name so only
      tools the CEO doesn't already have via the VP inherit through.
    """
    from backend.graph.tiers.vice_president import real_tools as vp_real_tools
    from backend.mcp.registry import get_registry

    vp_tools = vp_real_tools()
    vp_tool_names = {t.name for t in vp_tools}
    ceo_only_mcp_tools = [
        t for t in get_registry().tools_for_tier(Tier.CEO) if t.name not in vp_tool_names
    ]
    return [*vp_tools, *ceo_only_mcp_tools, make_escalate_to_human_tool()]


def stub_tools() -> list[BaseTool]:
    """VP stubs plus a stub notify_human(). Kept for tests that want
    tool-calling plumbing without a live registry or notification config."""
    from langchain_core.tools import tool

    from backend.graph.tiers.vice_president import stub_tools as vp_stub_tools

    @tool
    def notify_human(reason: str) -> str:
        """Loop in a human admin when every automated option is exhausted."""
        return f"STUB: would notify the human admin now (reason: {reason!r})."

    return [*vp_stub_tools(), notify_human]


# TODO(M5): output guardrails apply here and nowhere else — this is the last tier
#   before the customer. Check for hallucinated commitments, leaked internals,
#   and unsafe advice.

_ = Tier  # staged for the implementation above
