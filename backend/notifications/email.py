"""Email escalation to the human admin.  (M4)"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.graph.handoff import HandoffPacket


# TODO(M4): ESCALATION_EMAIL_TEMPLATE
#   Built from the HandoffPacket, not the transcript — the same summarization
#   protocol, a different consumer. An admin opening this at 2am should be able
#   to act without reading 40 messages.
#
#   Sections: what the customer wants (customer_intent), what is known
#   (verified_facts), what has been tried (attempted_actions), what is ruled out,
#   what is still open, why it reached the CEO, and a link back to the live session.


async def send_escalation_email(
    packet: HandoffPacket,
    to_address: str,
    session_url: str,
    urgency: str = "normal",
) -> bool:
    """TODO(M4): send via aiosmtplib using the SMTP_* env vars.

    Returns success. On failure, log and return False — do NOT raise. A dead SMTP
    server must not break the customer's conversation; the CEO falls back to the
    other channels and tells the customer honestly what happened.

    TODO(M4): include the session URL so the admin can join the live conversation
      rather than starting a separate email thread with the customer.
    """
    raise NotImplementedError


def smtp_configured() -> bool:
    """TODO(M4): true when SMTP_HOST/USER/PASSWORD are all set.

    Checked at startup so a misconfigured deployment is caught before a customer
    ever needs the channel.
    """
    raise NotImplementedError


_ = os  # staged for the implementations above
