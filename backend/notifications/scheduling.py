"""Call scheduling for the customer.  (M4)

The lightest of the three channels: surface `human_admin.scheduling_link` as an
inline affordance in the chat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.graph.handoff import HandoffPacket


def build_scheduling_offer(
    packet: HandoffPacket,
    scheduling_link: str,
) -> dict:
    """TODO(M4): payload for the frontend's scheduling affordance.

        {"type": "scheduling_offer", "link", "context_summary", "ticket_id"}

    TODO(M4): append ticket_id as a query param so whoever takes the call has the
      packet waiting. A scheduled call where the human asks the customer to
      explain everything again defeats the entire handoff protocol.
    """
    raise NotImplementedError


# TODO(M4): the offer is a SUGGESTION, not a session terminator. The customer may
#   ignore it entirely and keep chatting with the CEO — that path must keep working.

# TODO(M5 / optional): real calendar integration (Cal.com, Google Calendar) to
#   show actual availability instead of a bare link. Only worth it if someone asks.
