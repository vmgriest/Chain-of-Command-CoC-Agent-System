"""Web Push notification to the human admin.  (M4)"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.graph.handoff import HandoffPacket

# TODO(M4): generate VAPID keys once (`vapid --gen`) into VAPID_PUBLIC_KEY /
#   VAPID_PRIVATE_KEY. Regenerating invalidates every existing subscription.


async def send_push(
    packet: HandoffPacket,
    topic: str,
    session_url: str,
    urgency: str = "normal",
) -> bool:
    """TODO(M4): push a short notification to admins subscribed to `topic`.

    A push payload is small — a one-line summary from packet.customer_intent plus
    a deep link. The detail belongs in the email; this is just the nudge.

    Returns success; logs and returns False on failure. Same reasoning as email:
    a failed notification must not break the conversation.
    """
    raise NotImplementedError


# TODO(M4): subscription storage.
#   Web Push needs a persisted subscription object per admin device. For M4 a
#   JSON file is fine; note it as a database item when auth lands.

# TODO(M4): register_subscription(subscription, topic) -> None
# TODO(M4): a POST /api/push/subscribe endpoint for the admin client.

_ = os  # staged for the implementations above
