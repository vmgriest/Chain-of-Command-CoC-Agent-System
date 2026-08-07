/**
 * Scrollback. Renders messages plus inline TierTransition markers.
 */

// TODO(M1): MessageList
//   - Map over store.messages
//   - Each message renders in ITS OWN tier's styling, not the current tier's.
//     Scrolling up should show the whole journey — Penny's slate, then Dwight's
//     amber — which makes the escalation history legible after the fact.
//   - Transition markers render as <TierTransition /> between messages
//
// TODO(M1): auto-scroll to bottom on new content, but ONLY when the user is
//   already near the bottom. Yanking the view while someone is reading
//   scrollback is a small betrayal.
//
// TODO(M1): streaming messages show a cursor/pulse until finishAgentMessage().
//
// TODO(M1): accessibility — aria-live="polite" on the message region so screen
//   readers announce replies. Announce tier changes explicitly; a purely visual
//   theme swap conveys nothing to a screen reader user, and the escalation is
//   the single most important state change in the product.

export function MessageList(): JSX.Element {
  throw new Error('not implemented');
}
