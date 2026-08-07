/**
 * The escalation divider — the visual centerpiece.
 *
 * Rendered inline in the message list when a tier_change arrives, and it STAYS
 * in scrollback. The conversation becomes a visible record of the journey up the
 * ladder rather than a flat transcript that mysteriously changes color.
 */

// TODO(M1): TierTransition({ event }: { event: TierChangeEvent })
//
//   Content:
//     - "Penny → Dwight" with both tier badges
//     - The escalation reason, phrased as a capability gap
//     - packet_summary: "Carrying over: account #48812, Okta IdP, cert issues
//       ruled out"
//
//   ⚠ packet_summary is the payoff of the whole handoff protocol. Showing the
//     customer exactly what was carried forward is what distinguishes this from
//     a phone tree that makes you repeat yourself. Make it prominent, not a
//     footnote.
//
// TODO(M1): Framer Motion — divider scales in horizontally, content fades up,
//   ~400ms. Coordinated with useEscalation's sequence.
//
// TODO(M1): prefers-reduced-motion — render statically. The divider and its
//   content must survive; only the motion is optional.

export function TierTransition(): JSX.Element {
  throw new Error('not implemented');
}
