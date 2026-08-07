/**
 * Status banner shown after the CEO involves a human.  (M4)
 *
 * ⚠ THE CHAT CONTINUES UNDERNEATH THIS. The banner is informational — it is not
 *   a terminal state, and the input must stay enabled. The intuitive
 *   implementation is to disable the composer once a human is looped in; that is
 *   exactly what must not happen.
 */

// TODO(M4): HumanEscalationBanner({ event }: { event: HumanEscalationEvent })
//
//   Renders:
//     - What was done: "I've emailed our support lead and sent them everything
//       we've covered."
//     - What happens next, with a rough timeframe if one is known
//     - The scheduling link as an optional affordance, if present
//     - Nothing that reads like "this conversation has ended"
//
// TODO(M4): sticky at the top of the message area, dismissible to a compact pill.
//   It should not consume vertical space for the rest of the conversation.
//
// TODO(M4): the scheduling link is an OFFER. Ignoring it and continuing to chat
//   with the CEO must keep working — that is the path most customers will take.

export function HumanEscalationBanner(): JSX.Element {
  throw new Error('not implemented');
}
