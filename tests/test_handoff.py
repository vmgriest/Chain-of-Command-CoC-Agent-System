"""Handoff protocol tests.  (M1)

The behavioural claims here — facts accumulate, the packet stays bounded, PII
does not survive — are the ones worth guarding closely. The strongest ones live
in test_invariants.py; this file covers the details around them.
"""

from __future__ import annotations

import pytest

# --- redaction ------------------------------------------------------------

# TODO(M1): test_redact_email / test_redact_phone / test_redact_card
#   Each replaced with a TYPED placeholder, not blanked. A downstream tier needs
#   to know an email was present in order to ask for it again.

# TODO(M1): test_redact_returns_false_when_clean
#   Clean text -> (unchanged, False), so pii_redacted stays accurate.

# TODO(M1): test_redact_does_not_mangle_order_ids
#   False positives matter as much as misses — an order number eaten by the card
#   regex breaks the conversation in a way nobody will trace back to redaction.


# --- packet construction --------------------------------------------------

# TODO(M1): test_initial_packet_is_empty
#   New session: every list empty, escalation_reason "".

# TODO(M1): test_packet_enforces_max_length
#   Constructing with more than MAX_FACTS entries -> ValidationError.

# TODO(M1): test_estimated_tokens_is_reasonable
#   Rough, but must track packet size monotonically.


# --- summarization --------------------------------------------------------

# TODO(M1): test_summarizer_merges_incoming_packet
#   Facts in the incoming packet appear in the outgoing one. Accumulation is the
#   whole point of passing `incoming` — a summarizer that starts fresh each hop
#   loses everything the Front Desk learned.

# TODO(M1): test_summarizer_records_failures_in_ruled_out
#   A failed attempt in the transcript ends up in ruled_out with a reason.

# TODO(M1): test_summarizer_does_not_invent_facts
#   Facts absent from the transcript must not appear. Hardest to test well —
#   scripted fake_llm plus a spot-check against a real model.

# TODO(M1): test_over_budget_triggers_resummarization
#   Oversized result -> one aggressive retry -> truncate. Must not loop.

# TODO(M1): test_summarizer_uses_destination_model
#   The larger model of the two, and the one that has to act on the result.

_ = pytest
