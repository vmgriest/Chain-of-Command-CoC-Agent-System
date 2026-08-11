"""Call scheduling for the customer.  (M4)

The lightest of the three channels: surface `human_admin.scheduling_link` as an
inline affordance in the chat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

if TYPE_CHECKING:
    from backend.graph.handoff import HandoffPacket


def build_scheduling_offer(
    packet: HandoffPacket,
    scheduling_link: str,
) -> dict:
    """Payload for the frontend's scheduling affordance.

        {"type": "scheduling_offer", "link", "context_summary", "ticket_id"}

    Appends ticket_id as a query param so whoever takes the call has the
    packet waiting. A scheduled call where the human asks the customer to
    explain everything again defeats the entire handoff protocol.

    The offer is a SUGGESTION, not a session terminator — the customer may
    ignore it entirely and keep chatting with the CEO. That path is untouched
    by this function; it only builds a payload, never advances the graph.
    """
    parsed = urlparse(scheduling_link)
    query = [*parse_qsl(parsed.query), ("ticket_id", packet.ticket_id)]
    link_with_ticket = urlunparse(parsed._replace(query=urlencode(query)))

    return {
        "type": "scheduling_offer",
        "link": link_with_ticket,
        "context_summary": packet.customer_intent or "Support escalation",
        "ticket_id": packet.ticket_id,
    }


# TODO(M5 / optional): real calendar integration (Cal.com, Google Calendar) to
#   show actual availability instead of a bare link. Only worth it if someone asks.
