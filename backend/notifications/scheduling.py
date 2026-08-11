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
    # urlparse/parse_qsl/urlencode/urlunparse is the standard-library round trip
    # for "take a URL, add one query param, put it back together" without
    # clobbering any query params the link already had (e.g. Cal.com's own
    # ?duration= or ?month= params).
    parsed = urlparse(scheduling_link)
    query = [*parse_qsl(parsed.query), ("ticket_id", packet.ticket_id)]
    link_with_ticket = urlunparse(parsed._replace(query=urlencode(query)))

    return {
        "type": "scheduling_offer",
        "link": link_with_ticket,
        "context_summary": packet.customer_intent or "Support escalation",
        "ticket_id": packet.ticket_id,
    }


# Deliberately just a real, clickable booking link (e.g. a Cal.com URL from
# company_config.json's human_admin.scheduling_link) rather than a live
# calendar-availability widget — a real calendar integration (showing actual
# open slots inline) would be the natural next step if this needed to feel
# more custom, but wasn't asked for.
