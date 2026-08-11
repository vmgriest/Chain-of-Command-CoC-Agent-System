"""Notification channels: email, scheduling, and the notify_human fan-out.  (M4)

Real sends (SMTP) are a network boundary and are faked here, same convention
as the RAG/MCP test suites. notify_human's channel-selection logic against a
real (unconfigured) SMTP setup was additionally live-verified by hand — see
CHECKLIST.md.
"""

from __future__ import annotations

import pytest


def _packet():
    from backend.graph.handoff import initial_packet

    packet = initial_packet("coc_notify_test")
    packet.customer_intent = "Wants an exception to the return policy"
    packet.escalation_reason = "requires executive judgment"
    return packet


# ---------------------------------------------------------------------------
# email
# ---------------------------------------------------------------------------


def test_smtp_configured_requires_all_three_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.notifications.email import smtp_configured

    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert smtp_configured() is False

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    assert smtp_configured() is True


@pytest.mark.asyncio
async def test_send_escalation_email_returns_false_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.notifications.email import send_escalation_email

    monkeypatch.delenv("SMTP_HOST", raising=False)
    result = await send_escalation_email(_packet(), "admin@example.com", "http://x/session")
    assert result is False


@pytest.mark.asyncio
async def test_send_escalation_email_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.notifications.email as email_module

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")

    calls = {}

    async def _fake_send(message, **kwargs):
        calls["subject"] = message["Subject"]
        calls["to"] = message["To"]
        calls["body"] = message.get_content()
        calls["kwargs"] = kwargs

    monkeypatch.setattr("aiosmtplib.send", _fake_send)

    result = await email_module.send_escalation_email(
        _packet(), "admin@example.com", "http://x/session/coc_notify_test", urgency="urgent"
    )

    assert result is True
    assert calls["to"] == "admin@example.com"
    assert "coc_notify_test" in calls["subject"]
    assert "requires executive judgment" in calls["body"]
    assert "http://x/session/coc_notify_test" in calls["body"]


@pytest.mark.asyncio
async def test_send_escalation_email_failure_is_caught_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.notifications.email import send_escalation_email

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")

    async def _boom(*_a, **_kw):
        msg = "smtp server unreachable"
        raise OSError(msg)

    monkeypatch.setattr("aiosmtplib.send", _boom)

    result = await send_escalation_email(_packet(), "admin@example.com", "http://x")
    assert result is False  # must not raise — a dead SMTP server can't break the chat


# ---------------------------------------------------------------------------
# scheduling
# ---------------------------------------------------------------------------


def test_build_scheduling_offer_appends_ticket_id() -> None:
    from backend.notifications.scheduling import build_scheduling_offer

    packet = _packet()
    offer = build_scheduling_offer(packet, "https://cal.acme.com/support")

    assert offer["type"] == "scheduling_offer"
    assert offer["ticket_id"] == packet.ticket_id
    assert f"ticket_id={packet.ticket_id}" in offer["link"]
    assert offer["link"].startswith("https://cal.acme.com/support")


def test_build_scheduling_offer_preserves_existing_query_params() -> None:
    from backend.notifications.scheduling import build_scheduling_offer

    packet = _packet()
    offer = build_scheduling_offer(packet, "https://cal.acme.com/support?team=escalations")

    assert "team=escalations" in offer["link"]
    assert "ticket_id=" in offer["link"]


# ---------------------------------------------------------------------------
# notify_human fan-out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_human_skips_unconfigured_channels(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    """Reflects the real config used in dev: email configured but SMTP env
    vars are not — must be skipped without raising, and scheduling (which is
    just a link, not a send) still counts."""
    from backend.notifications import notify_human

    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setattr("backend.config.loader.get_config", lambda: config)

    channels = await notify_human(_packet(), "reason", "normal", "http://x/session")
    assert channels == ["scheduling"]


@pytest.mark.asyncio
async def test_notify_human_excludes_failed_email_channel(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    from backend.notifications import notify_human

    monkeypatch.setattr("backend.config.loader.get_config", lambda: config)
    monkeypatch.setattr("backend.notifications.email.smtp_configured", lambda: True)

    async def _email_fails(*_a, **_kw):
        return False

    monkeypatch.setattr("backend.notifications.email.send_escalation_email", _email_fails)

    channels = await notify_human(_packet(), "reason", "normal", "http://x/session")
    assert channels == ["scheduling"]  # email attempted but failed -> absent


@pytest.mark.asyncio
async def test_notify_human_includes_succeeded_email_channel(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    from backend.notifications import notify_human

    monkeypatch.setattr("backend.config.loader.get_config", lambda: config)
    monkeypatch.setattr("backend.notifications.email.smtp_configured", lambda: True)

    async def _email_ok(*_a, **_kw):
        return True

    monkeypatch.setattr("backend.notifications.email.send_escalation_email", _email_ok)

    channels = await notify_human(_packet(), "reason", "normal", "http://x/session")
    assert channels == ["email", "scheduling"]
