/**
 * Message composer.
 */

// TODO(M1): MessageInput
//   - Textarea, Enter to send, Shift+Enter for newline
//   - Auto-resize up to a max height
//   - Send via useWebSocket().send({ type: 'user_message', content })
//
// TODO(M1): disable while:
//     - transitioning (a message sent mid-handoff has an ambiguous destination)
//     - a pending escalation or context prompt is open (answer it first)
//     - disconnected (queue instead, and say so)
//   Each case needs its own placeholder text. A generically disabled input with
//   no explanation reads as a broken app.
//
// TODO(M1): keep focus after send, and after a tier transition completes.

export function MessageInput(): JSX.Element {
  throw new Error('not implemented');
}
