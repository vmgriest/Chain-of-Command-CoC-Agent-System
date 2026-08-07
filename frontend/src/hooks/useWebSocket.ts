/**
 * WebSocket connection to /ws/chat/{sessionId}.
 *
 * Owns connect, reconnect, and typed event dispatch into the chat store.
 * Components never touch the socket directly.
 */

import type { ClientEvent } from '@/types';

// TODO(M1): useWebSocket(sessionId) -> { send, connected, reconnecting }
//
//   - Connect on mount, close on unmount
//   - Parse each inbound message and dispatch by `type` into the store
//   - Exponential backoff on reconnect (1s, 2s, 4s, 8s, capped at 30s)
//   - Queue outbound messages while disconnected; flush on reconnect
//
// TODO(M1): on reconnect the SERVER re-sends any pending escalation_prompt or
//   context_request. The client must handle receiving a prompt it has already
//   seen — replacing the pending state is fine, duplicating it into the message
//   list is not.
//
// TODO(M1): distinguish a clean close (code 1000) from a drop. Only show the
//   "reconnecting" indicator on a real drop, or every navigation flashes it.

export function useWebSocket(_sessionId: string): {
  send: (event: ClientEvent) => void;
  connected: boolean;
  reconnecting: boolean;
} {
  throw new Error('not implemented');
}
