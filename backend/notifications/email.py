"""Email escalation to the human admin.  (M4)"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.graph.handoff import HandoffPacket

logger = logging.getLogger("coc.notifications.email")

# Built from the HandoffPacket, not the transcript — the same summarization
# protocol, a different consumer. An admin opening this at 2am should be able
# to act without reading 40 messages.
ESCALATION_EMAIL_TEMPLATE = """\
A customer conversation has reached the CEO tier and needs a human follow-up.

Ticket: {ticket_id}
Urgency: {urgency}

Customer's goal:
  {customer_intent}

Known facts:
{verified_facts}

Already tried:
{attempted_actions}

Already ruled out:
{ruled_out}

Still open:
{open_questions}

Why this reached you:
  {escalation_reason}

Join the live session: {session_url}
"""


def _bulleted(items: list[str]) -> str:
    return "\n".join(f"  - {item}" for item in items) if items else "  (none)"


def _actions_bulleted(actions: list) -> str:
    if not actions:
        return "  (none)"
    return "\n".join(f"  - [{a.tier}] {a.action} -> {a.outcome}" for a in actions)


def _render_body(packet: HandoffPacket, session_url: str, urgency: str) -> str:
    return ESCALATION_EMAIL_TEMPLATE.format(
        ticket_id=packet.ticket_id,
        urgency=urgency,
        customer_intent=packet.customer_intent or "(not established)",
        verified_facts=_bulleted(packet.verified_facts),
        attempted_actions=_actions_bulleted(packet.attempted_actions),
        ruled_out=_bulleted(packet.ruled_out),
        open_questions=_bulleted(packet.open_questions),
        escalation_reason=packet.escalation_reason,
        session_url=session_url,
    )


async def send_escalation_email(
    packet: HandoffPacket,
    to_address: str,
    session_url: str,
    urgency: str = "normal",
) -> bool:
    """Send via aiosmtplib using the SMTP_* env vars.

    Returns success. On failure, log and return False — do NOT raise. A dead SMTP
    server must not break the customer's conversation; the CEO falls back to the
    other channels and tells the customer honestly what happened.
    """
    if not smtp_configured():
        logger.warning("send_escalation_email called but SMTP is not fully configured")
        return False

    from email.message import EmailMessage

    import aiosmtplib

    message = EmailMessage()
    message["Subject"] = f"[Chain of Command] Escalation — {packet.ticket_id} ({urgency})"
    message["From"] = os.environ.get("SMTP_FROM") or os.environ["SMTP_USER"]
    message["To"] = to_address
    message.set_content(_render_body(packet, session_url, urgency))

    try:
        await aiosmtplib.send(
            message,
            hostname=os.environ["SMTP_HOST"],
            port=int(os.environ.get("SMTP_PORT", "587")),
            username=os.environ.get("SMTP_USER"),
            password=os.environ.get("SMTP_PASSWORD"),
            start_tls=True,  # upgrade the plain connection to TLS before sending
            # credentials/content — matches port 587 (submission), not 465 (implicit TLS)
        )
    except Exception:
        logger.exception("Failed to send escalation email for ticket %s", packet.ticket_id)
        return False
    return True


def smtp_configured() -> bool:
    """True when SMTP_HOST/USER/PASSWORD are all set.

    Checked at startup so a misconfigured deployment is caught before a customer
    ever needs the channel.
    """
    return bool(
        os.environ.get("SMTP_HOST")
        and os.environ.get("SMTP_USER")
        and os.environ.get("SMTP_PASSWORD")
    )
