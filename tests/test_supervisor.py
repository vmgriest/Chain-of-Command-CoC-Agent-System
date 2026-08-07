"""Supervisor routing and escalation tests.  (M1)"""

from __future__ import annotations

import pytest

# --- intent classification ------------------------------------------------

# TODO(M1): test_classifies_escalation_phrasings
#   All must classify as wants_escalation, sharing no keywords:
#     "I want to talk to upper management"
#     "can I speak to someone more senior"
#     "is there a manager around"
#     "you're not helping, who's your boss"
#   This is why it is a classifier and not a keyword match.

# TODO(M1): test_complaint_is_not_escalation_request
#   "this is really frustrating" is NOT a request to escalate. Escalating every
#   frustrated customer defeats the tiering.


# --- routing --------------------------------------------------------------

# TODO(M1): test_user_escalation_skips_consent  (also in test_invariants.py)
# TODO(M1): test_agent_escalation_requires_consent
# TODO(M1): test_consent_waived_when_config_disables_it
#   require_user_consent: false -> escalate directly.

# TODO(M1): test_max_attempts_forces_escalation
#   After max_attempts_per_tier unresolved turns, the tier stops insisting it can
#   cope. Without this a stubborn small model loops forever at the Front Desk.

# TODO(M1): test_ceo_escalation_routes_to_human
#   wants_escalation at the CEO goes to the human path, not off the top of the
#   ladder.

# TODO(M1): test_full_four_hop_escalation
#   front_desk -> manager -> vice_president -> ceo, with an intro at each stop
#   and an accumulating packet. The end-to-end happy path.


# --- transitions ----------------------------------------------------------

# TODO(M1): test_handoff_resets_attempt_count
# TODO(M1): test_handoff_sets_tier_just_changed
#   Drives the self-introduction.
# TODO(M1): test_tier_change_event_carries_theme
#   The frontend needs `theme` to re-render; a transition without it is invisible.


# --- checkpointing --------------------------------------------------------

# TODO(M1): test_resume_after_interrupt
#   Interrupt, discard the in-memory graph, rebuild from checkpoint, resume.
#   Simulates a browser refresh.

# TODO(M1): test_resume_replays_pending_prompt
#   On reconnect while paused, the pending escalation_prompt / context_request is
#   RE-SENT. Otherwise the customer sees a dead chat waiting on an answer to a
#   question the UI no longer shows.

_ = pytest
