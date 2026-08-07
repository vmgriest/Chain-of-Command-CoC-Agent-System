/**
 * Context request — the agent needs a specific fact to continue.
 *
 * ⚠ INLINE, not a modal. Same reasoning as EscalationPrompt.
 *
 * ⚠ CONDITIONAL. This appears only when the agent genuinely needs something. Most
 *   turns render nothing here. If it starts showing up every turn, the backend's
 *   needs_context logic has regressed into a per-turn checkpoint.
 */

// TODO(M1): ContextRequest({ event }: { event: ContextRequestEvent })
//
//   Renders the agent's question ("To pull up your billing history I'll need
//   your account number.") with a focused input and a submit button.
//
// TODO(M1): on submit, send { type: 'context_response', answer } and clear the
//   pending state. The graph resumes from its interrupt.
//
// TODO(M1): allow declining. A customer who will not share an account number
//   should be able to say so and have the agent work around it or escalate —
//   not sit blocked on an unanswerable question.
//
// TODO(M5): the answer often contains PII. It is redacted at the tier boundary
//   server-side (backend/graph/handoff.py), but consider not persisting raw
//   answers to localStorage on the client either.

export function ContextRequest(): JSX.Element {
  throw new Error('not implemented');
}
