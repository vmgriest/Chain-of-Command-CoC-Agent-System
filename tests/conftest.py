"""Shared fixtures.

Most of these are deterministic fakes. Tests that need a real Ollama model
should be marked and skipped by default — a suite that requires a GPU is a suite
nobody runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("COMPANY_CONFIG_PATH", "company_config.example.json")

REPO_ROOT = Path(__file__).resolve().parent.parent


class _FakeStructuredRunnable:
    """Returned by FakeLLM.with_structured_output(schema). Yields the next
    scripted value for that schema, or falls back to a default constructed
    with no arguments if the schema supports it."""

    def __init__(self, fake_llm: FakeLLM, schema: type) -> None:
        self._fake_llm = fake_llm
        self._schema = schema

    async def ainvoke(self, *_args, **_kwargs):
        return self._fake_llm._next_structured(self._schema)

    def invoke(self, *_args, **_kwargs):
        return self._fake_llm._next_structured(self._schema)


class FakeLLM:
    """A stand-in chat model exposing the slice of the LangChain Runnable
    interface backend/graph code relies on: ainvoke, astream, bind_tools,
    with_structured_output. Scripted per test so escalation logic can be
    exercised without a real model.
    """

    def __init__(self) -> None:
        self._text_responses: list = []
        self._structured_responses: dict[type, list] = {}

    def script_text(self, *messages) -> FakeLLM:
        """Queue plain AIMessage responses for .ainvoke()/.astream() (the
        tier's main "agent" node)."""
        self._text_responses.extend(messages)
        return self

    def script_structured(self, schema: type, *values) -> FakeLLM:
        """Queue structured-output return values for a given schema, e.g.
        script_structured(TierVerdict, TierVerdict(can_resolve=True, ...))."""
        self._structured_responses.setdefault(schema, []).extend(values)
        return self

    def _next_structured(self, schema: type):
        queue = self._structured_responses.get(schema)
        if not queue:
            msg = f"FakeLLM: no scripted structured response left for {schema.__name__}"
            raise AssertionError(msg)
        return queue.pop(0)

    # --- Runnable-ish surface used by backend/graph -----------------------

    def bind_tools(self, _tools):
        return self

    def with_structured_output(self, schema: type, **_kwargs):
        return _FakeStructuredRunnable(self, schema)

    async def ainvoke(self, *_args, **_kwargs):
        from langchain_core.messages import AIMessage

        if self._text_responses:
            next_ = self._text_responses.pop(0)
            return next_ if hasattr(next_, "content") else AIMessage(content=str(next_))
        return AIMessage(content="")

    async def astream(self, *args, **kwargs):
        msg = await self.ainvoke(*args, **kwargs)
        yield msg


@pytest.fixture
def example_config_dict() -> dict:
    """Loads company_config.example.json as a raw dict."""
    with (REPO_ROOT / "company_config.example.json").open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def config(example_config_dict: dict):
    """Parsed CompanyConfig from the example (with `_comment` stripped, as the
    loader does)."""
    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    return CompanyConfig.model_validate(raw)


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def transcript_with_pii():
    """Messages containing an email, a phone number, and a card number."""
    from langchain_core.messages import AIMessage, HumanMessage

    return [
        HumanMessage(content="My email is jane.doe@example.com and my phone is 415-555-0134."),
        AIMessage(content="Thanks, I've noted that."),
        HumanMessage(content="Also here's my card: 4111 1111 1111 1111 if that helps."),
    ]


@pytest.fixture
def populated_packet():
    """A HandoffPacket with facts, attempted actions, and ruled_out entries."""
    from backend.config.schema import Tier
    from backend.graph.handoff import AttemptedAction, HandoffPacket

    return HandoffPacket(
        ticket_id="coc_test123",
        customer_intent="Cannot complete SSO setup; SAML assertion rejected",
        verified_facts=["Account #48812, Enterprise tier", "Okta as IdP"],
        attempted_actions=[
            AttemptedAction(
                tier=Tier.FRONT_DESK,
                action="walked through standard SSO checklist",
                outcome="no resolution",
            )
        ],
        ruled_out=["expired certificate", "clock skew"],
        open_questions=["Is the customer's IdP metadata current?"],
        sentiment="frustrated",
        escalation_reason="requires external MCP access to the identity provider",
    )
