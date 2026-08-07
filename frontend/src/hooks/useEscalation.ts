/**
 * Escalation transitions: theme swap and animation sequencing.
 *
 * This is the moment that sells the whole concept — the customer must be certain
 * they moved up, not stalled. It gets more care than a theme swap normally would.
 */

import type { Theme } from '@/themes';
import type { Tier } from '@/types';

// TODO(M1): useEscalation() -> { currentTier, theme, transitioning, respondToEscalation }
//
//   Transition sequence on a tier_change event:
//     1. transitioning = true
//     2. Fade the outgoing agent's header (~200ms)
//     3. Animate in the TierTransition divider — from/to personas plus
//        packet_summary, so the handoff is legible rather than implied
//     4. Cross-fade the CSS custom properties (~400ms)
//     5. Stream in the new agent's introduction
//     6. transitioning = false
//
//   Total ~800ms. Long enough to register as an event, short enough not to feel
//   like the app hung.
//
// TODO(M1): respect prefers-reduced-motion — skip the animation, keep the
//   divider and the theme change. The information must survive; only the motion
//   is optional.
//
// TODO(M1): block user input while transitioning. A message sent mid-handoff has
//   an ambiguous destination.

export function useEscalation(): {
  currentTier: Tier;
  theme: Theme;
  transitioning: boolean;
  respondToEscalation: (approved: boolean) => void;
} {
  throw new Error('not implemented');
}
