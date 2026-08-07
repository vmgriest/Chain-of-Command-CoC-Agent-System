"""Per-tier behaviour tests.  (M1+)"""

from __future__ import annotations

import pytest

# --- shared loop (base.py) ------------------------------------------------

# TODO(M1): test_build_tier_with_no_tools_omits_tool_node
# TODO(M1): test_build_tier_with_tools_includes_tool_node
# TODO(M1): test_persona_name_comes_from_config
#   Rename the persona in config; the introduction changes. Nothing hardcoded.

# TODO(M1): test_verdict_sets_escalation_reason_when_stuck
#   can_resolve False must come with a specific reason, not None and not vague.

# TODO(M1): test_attempt_count_increments_on_unresolved_turn


# --- front desk -----------------------------------------------------------

# TODO(M1): test_front_desk_admits_knowledge_limits
#   Asked about something past its cutoff, it says so and offers to escalate
#   rather than confabulating. This is the tier's defining behaviour.

# TODO(M5): test_off_scope_question_is_declined_not_escalated
#   Off-topic questions get declined politely. Escalating them just moves the
#   problem up the ladder.


# --- manager --------------------------------------------------------------

# TODO(M2): test_manager_cites_sources
#   RAG-backed answers carry citations. Uncited claims are not acceptable.

# TODO(M2): test_manager_escalates_when_rag_empty
#   Empty retrieval is a valid signal, and grounds for escalation — not a cue to
#   answer from the model's own memory.

# TODO(M2): test_scrape_url_rejects_off_allowlist
#   Including redirects that leave the allowlist. Same SSRF hole with an extra step.


# --- vice president -------------------------------------------------------

# TODO(M3): test_vp_receives_external_mcp_tools
# TODO(M3): test_vp_parallelizes_independent_tool_calls
#   asyncio.gather over different tools. Calls to the SAME tool may have ordering
#   dependencies — only parallelize across distinct tools.


# --- ceo ------------------------------------------------------------------

# TODO(M4): test_optimizer_loop_terminates
#   Bounded by iterations AND tokens. Returns the best draft on exhaustion,
#   never an error — an imperfect answer beats a failure.

# TODO(M4): test_evaluator_is_separate_call
#   Not the drafter grading itself. One call doing both produces agreeable nonsense.

# TODO(M4): test_ceo_answers_simple_followup_without_escalating
#   "What's your refund window?" at CEO tier is just answered. No descalation,
#   no human escalation for something trivial.

_ = pytest
