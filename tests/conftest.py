"""Shared fixtures.

Most of these are deterministic fakes. Tests that need a real Ollama model
should be marked and skipped by default — a suite that requires a GPU is a suite
nobody runs.
"""

from __future__ import annotations

import pytest

# TODO(M1): fixture `example_config_dict` — loads company_config.example.json.
# TODO(M1): fixture `config` — parsed CompanyConfig from the example.

# TODO(M1): fixture `fake_llm` — returns scripted responses so escalation logic
#   can be tested without a model. Must support .with_structured_output() since
#   TierVerdict, UserIntent, and HandoffPacket all depend on it.

# TODO(M1): fixture `transcript_with_pii` — messages containing an email, a
#   phone number, and a card number, for redaction tests.

# TODO(M1): fixture `populated_packet` — a HandoffPacket with facts, attempted
#   actions, and ruled_out entries, for accumulation tests.

# TODO(M1): fixture `graph` — compiled supervisor graph wired to fake_llm and an
#   in-memory checkpointer.

# TODO(M2): marker `requires_ollama`, skipped unless OLLAMA_BASE_URL responds.
# TODO(M2): marker `requires_qdrant`, same idea.
# TODO(M3): marker `requires_docker`, same idea.

_ = pytest
