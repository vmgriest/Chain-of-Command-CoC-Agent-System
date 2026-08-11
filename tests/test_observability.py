"""Tracing config + analytics tests.  (M5)"""

from __future__ import annotations

import pytest


def _state(**overrides) -> dict:
    from backend.config.schema import Tier

    base = {
        "ticket_id": "coc_obs_test",
        "current_tier": Tier.FRONT_DESK,
        "human_notified": False,
        "turn_count": 3,
        "started_at": 0.0,
        "escalation_reasons": [],
        "user_initiated_escalations": 0,
        "agent_initiated_escalations": 0,
        "consent_refusals": 0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# init_tracing
# ---------------------------------------------------------------------------


def test_init_tracing_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.observability.tracing import init_tracing

    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    init_tracing()
    assert "LANGCHAIN_TRACING_V2" not in __import__("os").environ


def test_init_tracing_warns_without_api_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from backend.observability.tracing import init_tracing

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    with caplog.at_level("WARNING"):
        init_tracing()
    assert "LANGCHAIN_TRACING_V2" not in __import__("os").environ
    assert "LANGSMITH_API_KEY" in caplog.text


def test_init_tracing_sets_langchain_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from backend.observability.tracing import init_tracing

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "sk-test")
    monkeypatch.setenv("LANGSMITH_PROJECT", "coc-test")
    init_tracing()
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGCHAIN_API_KEY"] == "sk-test"
    assert os.environ["LANGCHAIN_PROJECT"] == "coc-test"


# ---------------------------------------------------------------------------
# metrics_from_state / record_ticket / aggregate_stats
# ---------------------------------------------------------------------------


def test_metrics_from_state_resolved_when_not_human_escalated() -> None:
    from backend.config.schema import Tier
    from backend.observability.tracing import metrics_from_state

    metrics = metrics_from_state(_state(current_tier=Tier.MANAGER))
    assert metrics.resolved_at_tier == Tier.MANAGER
    assert metrics.tiers_traversed == 2
    assert metrics.human_escalated is False


def test_metrics_from_state_unresolved_when_human_escalated() -> None:
    from backend.observability.tracing import metrics_from_state

    metrics = metrics_from_state(_state(human_notified=True))
    assert metrics.resolved_at_tier is None
    assert metrics.human_escalated is True


def test_record_ticket_upserts_by_ticket_id(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.observability.tracing as tracing_module

    monkeypatch.setattr(tracing_module, "ANALYTICS_PATH", tmp_path / "analytics.json")

    metrics1 = tracing_module.metrics_from_state(_state(turn_count=1))
    tracing_module.record_ticket(metrics1)
    metrics2 = tracing_module.metrics_from_state(_state(turn_count=5))
    tracing_module.record_ticket(metrics2)

    stored = tracing_module._load_tickets()
    assert list(stored.keys()) == ["coc_obs_test"]  # same ticket, not duplicated
    assert stored["coc_obs_test"]["total_turns"] == 5  # latest write wins


def test_record_ticket_serializes_tier_as_string(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.observability.tracing as tracing_module

    monkeypatch.setattr(tracing_module, "ANALYTICS_PATH", tmp_path / "analytics.json")
    tracing_module.record_ticket(tracing_module.metrics_from_state(_state()))

    raw = (tmp_path / "analytics.json").read_text(encoding="utf-8")
    assert '"front_desk"' in raw  # JSON, not a repr like "<Tier.FRONT_DESK: ...>"


def test_aggregate_stats_empty_store(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.observability.tracing as tracing_module

    monkeypatch.setattr(tracing_module, "ANALYTICS_PATH", tmp_path / "does_not_exist.json")
    assert tracing_module.aggregate_stats() == {"ticket_count": 0}


def test_aggregate_stats_computes_expected_rollups(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.observability.tracing as tracing_module
    from backend.config.schema import Tier

    monkeypatch.setattr(tracing_module, "ANALYTICS_PATH", tmp_path / "analytics.json")

    tracing_module.record_ticket(
        tracing_module.metrics_from_state(_state(ticket_id="t1", current_tier=Tier.FRONT_DESK))
    )
    tracing_module.record_ticket(
        tracing_module.metrics_from_state(
            _state(
                ticket_id="t2",
                current_tier=Tier.MANAGER,
                agent_initiated_escalations=1,
                consent_refusals=1,
                escalation_reasons=["needs order lookup"],
            )
        )
    )
    tracing_module.record_ticket(
        tracing_module.metrics_from_state(
            _state(
                ticket_id="t3",
                current_tier=Tier.CEO,
                human_notified=True,
                user_initiated_escalations=1,
                escalation_reasons=["needs order lookup"],
            )
        )
    )

    stats = tracing_module.aggregate_stats()

    assert stats["ticket_count"] == 3
    assert stats["resolution_rate_per_tier"] == {
        "front_desk": pytest.approx(1 / 3),
        "manager": pytest.approx(1 / 3),
    }
    assert stats["human_escalation_rate"] == pytest.approx(1 / 3)
    assert stats["agent_initiated_escalations"] == 1
    assert stats["user_initiated_escalations"] == 1
    assert stats["consent_refusal_rate"] == pytest.approx(
        1.0
    )  # 1 refusal / 1 agent-initiated attempt
    assert stats["top_escalation_reasons"][0] == ("needs order lookup", 2)


def test_aggregate_stats_zero_agent_escalations_avoids_division_by_zero(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.observability.tracing as tracing_module

    monkeypatch.setattr(tracing_module, "ANALYTICS_PATH", tmp_path / "analytics.json")
    tracing_module.record_ticket(tracing_module.metrics_from_state(_state()))

    stats = tracing_module.aggregate_stats()
    assert stats["consent_refusal_rate"] == 0.0
