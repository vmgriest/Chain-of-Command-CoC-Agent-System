/**
 * Escalation consent prompt — the human-in-the-loop gate.
 *
 * ⚠ INLINE in the chat flow, NOT a modal. A modal frames escalation as an
 *   interruption to dismiss. Inline frames it as part of the conversation, which
 *   is what it is.
 *
 * Only appears for AGENT-initiated escalation. A customer who asked for a
 * manager is never asked to confirm.
 */

// TODO(M1): EscalationPrompt({ event }: { event: EscalationPromptEvent })
//
//   Renders:
//     - The agent's question, phrased around the capability gap:
//       "I don't have access to your billing records from this desk. Would you
//        like me to bring in a department manager who does?"
//     - Who they would be handed to (to_persona, to_title) — the customer should
//       know where they are going before agreeing
//     - Two buttons: "Yes, escalate" / "No, keep trying"
//
// TODO(M1): on answer, send { type: 'escalation_response', approved } and clear
//   the pending state immediately. The graph resumes from its interrupt.
//
// TODO(M1): refusal is a first-class outcome, not a dead end — the agent keeps
//   working at the current tier. Style "No" as an equal option, not a cancel.
//
// TODO(M1): keyboard accessible; focus the primary button on mount.

export function EscalationPrompt(): JSX.Element {
  throw new Error('not implemented');
}
