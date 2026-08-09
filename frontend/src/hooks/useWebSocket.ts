/**
 * WebSocket connection to /ws/chat/{sessionId}.
 *
 * Owns connect, reconnect, and typed event dispatch into the chat store.
 * Components never touch the socket directly.
 */

import { useCallback, useEffect, useRef } from 'react';

import { wsUrl } from '@/lib/api';
import { useChatStore } from '@/store/chat';
import type { ClientEvent, ServerEvent } from '@/types';

const MAX_BACKOFF_MS = 30_000;

/** Connects to /ws/chat/{sessionId}, dispatches inbound events into the chat
 *  store by `type`, and reconnects with exponential backoff on a real drop.
 *  Components never touch the socket directly — they call send() and read
 *  connection state from the store. */
export function useWebSocket(sessionId: string): {
  send: (event: ClientEvent) => void;
  connected: boolean;
  reconnecting: boolean;
} {
  const socketRef = useRef<WebSocket | null>(null);
  const queueRef = useRef<ClientEvent[]>([]);
  const backoffRef = useRef(1000);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connected = useChatStore((s) => s.connected);
  const reconnecting = useChatStore((s) => s.reconnecting);

  const dispatch = useCallback((event: ServerEvent) => {
    const store = useChatStore.getState();
    switch (event.type) {
      case 'token':
        store.appendToken(event.content);
        break;
      case 'agent_intro':
        store.startAgentMessage(event.tier, event.persona_name);
        break;
      case 'tier_change':
        store.finishAgentMessage();
        store.handleTierChange(event);
        break;
      case 'escalation_prompt':
        store.finishAgentMessage();
        store.setPendingEscalation(event);
        break;
      case 'context_request':
        store.finishAgentMessage();
        store.setPendingContext(event);
        break;
      case 'human_escalation':
        store.finishAgentMessage();
        store.setHumanEscalated(event);
        break;
      case 'error':
        store.finishAgentMessage();
        break;
      case 'turn_end':
        store.finishAgentMessage();
        store.setTurnInProgress(false);
        break;
      default:
        break;
    }
  }, []);

  useEffect(() => {
    // Scoped to THIS effect invocation, not a ref — a ref shared across
    // StrictMode's mount/unmount/remount would be reset by the new mount
    // before the old socket's async onclose fires, making the old socket
    // think it dropped unexpectedly and spawn a spurious extra reconnect.
    let closedByUs = false;

    function connect(): void {
      const socket = new WebSocket(wsUrl(sessionId));
      socketRef.current = socket;

      socket.onopen = () => {
        backoffRef.current = 1000;
        useChatStore.getState().setConnected(true);
        useChatStore.getState().setReconnecting(false);
        // Flush anything queued while disconnected.
        const queued = queueRef.current;
        queueRef.current = [];
        for (const event of queued) {
          socket.send(JSON.stringify(event));
        }
      };

      socket.onmessage = (raw) => {
        try {
          const event = JSON.parse(raw.data as string) as ServerEvent;
          // A resent pending prompt after reconnect replaces state rather than
          // appending — dispatch handles that uniformly via setPending*.
          dispatch(event);
        } catch {
          // Malformed frame — ignore rather than crash the socket handler.
        }
      };

      socket.onclose = (closeEvent) => {
        useChatStore.getState().setConnected(false);
        if (closedByUs) {
          return;
        }
        // Code 1000 is a clean close (e.g. tab navigating away) — no
        // reconnect indicator for that; only a real drop shows "reconnecting".
        if (closeEvent.code !== 1000) {
          useChatStore.getState().setReconnecting(true);
        }
        const delay = Math.min(backoffRef.current, MAX_BACKOFF_MS);
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
        reconnectTimerRef.current = setTimeout(connect, delay);
      };

      socket.onerror = () => {
        socket.close();
      };
    }

    connect();

    return () => {
      closedByUs = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      socketRef.current?.close(1000);
      socketRef.current = null;
    };
  }, [sessionId, dispatch]);

  const send = useCallback((event: ClientEvent) => {
    // Every ClientEvent kicks off exactly one server-side turn ending in
    // turn_end — flipping this here, in the one place all three event types
    // funnel through, is what keeps the composer locked until that arrives.
    useChatStore.getState().setTurnInProgress(true);
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(event));
    } else {
      queueRef.current.push(event);
    }
  }, []);

  return { send, connected, reconnecting };
}
