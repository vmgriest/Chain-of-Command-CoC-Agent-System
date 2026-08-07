/**
 * Persona header — who you are currently talking to.
 *
 * Shows the persona's real name from config plus the tier badge. The name is the
 * company's ("Jensen Huang"), the badge is the rung ("Office of the CEO"); both
 * matter and they are not the same thing.
 */

// TODO(M1): AgentHeader
//   - Avatar / monogram, themed per tier
//   - Persona name (from config) and title
//   - Tier badge with the rung label
//   - Optional ladder indicator (● ● ○ ○) showing position and headroom
//
// TODO(M1): animate name and badge on tier change, coordinated with
//   useEscalation's sequence — the header must not swap before the divider lands.
//
// TODO(M1): connection status indicator lives here. On reconnect, show it
//   without wiping the conversation — a dropped socket is not a lost session.

export function AgentHeader(): JSX.Element {
  throw new Error('not implemented');
}
