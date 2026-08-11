"""Human escalation channels for the CEO tier.  (M4)

email.py      — SMTP to human_admin.email
scheduling.py — surface human_admin.scheduling_link to the customer

⚠ Notifying a human NEVER ends the chat session. See backend/graph/tiers/ceo.py.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.graph.handoff import HandoffPacket

logger = logging.getLogger("coc.notifications")


def session_url(session_id: str) -> str:
    """Deep link an admin can open to see the live conversation.

    The frontend keeps session_id in localStorage rather than the URL (see
    frontend/src/hooks/useWebSocket.ts), so this is a query-param convention,
    not an existing route — a future admin view is what would consume it.
    """
    base = os.environ.get("APP_BASE_URL", "http://localhost:5173")
    return f"{base}?session={session_id}"


async def notify_human(
    packet: HandoffPacket, reason: str, urgency: str, session_url_: str
) -> list[str]:
    """Fan out to every channel configured in escalation.human_admin.

    Returns the channels that were actually attempted (email only counts if
    the send succeeded; scheduling is a customer-facing offer, not a send, so
    it counts whenever a link is configured). A channel that isn't
    configured, or a send that fails, is simply absent from the result — the
    CEO tier tells the customer honestly what happened either way; see
    backend/graph/supervisor.py::human_escalation_node.
    """
    from backend.config.loader import get_config
    from backend.notifications.email import send_escalation_email, smtp_configured

    admin = get_config().escalation.human_admin
    channels: list[str] = []

    if admin.email:
        if smtp_configured():
            if await send_escalation_email(packet, admin.email, session_url_, urgency):
                channels.append("email")
        else:
            logger.info("human_admin.email is set but SMTP is not configured — skipping email")

    if admin.scheduling_link:
        channels.append("scheduling")

    if not channels:
        logger.warning(
            "notify_human: no channel succeeded for ticket %s (reason: %s)",
            packet.ticket_id,
            reason,
        )

    return channels
