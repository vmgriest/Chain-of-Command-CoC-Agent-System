/**
 * Chat state (Zustand).
 *
 * Single source of truth for messages, the current tier, and any pending
 * interrupt. The WS hook dispatches into this; components only read.
 */

import type {
  ChatMessage,
  ContextRequestEvent,
  EscalationPromptEvent,
  PublicConfig,
  Tier,
} from '@/types';

export interface ChatState {
  // --- connection ---
  sessionId: string;
  connected: boolean;
  reconnecting: boolean;

  // --- conversation ---
  messages: ChatMessage[];
  currentTier: Tier;
  currentPersona: string;

  // --- pending interrupts (at most one at a time) ---
  pendingEscalation: EscalationPromptEvent | null;
  pendingContext: ContextRequestEvent | null;

  // --- human escalation (M4) ---
  // Sticky banner. Set once, never cleared — the chat continues underneath it.
  humanEscalated: boolean;
  humanEscalationMessage: string | null;
  schedulingLink: string | null;

  // --- config ---
  config: PublicConfig | null;
}

// TODO(M1): create the store with these actions:
//
//   appendUserMessage(content)
//   startAgentMessage(tier, personaName)  — placeholder with streaming: true
//   appendToken(content)                  — append to the streaming message
//   finishAgentMessage()                  — streaming: false
//
//   handleTierChange(event)   — set currentTier/currentPersona, insert a
//                               transition marker into the message list so the
//                               handoff is visible in scrollback afterwards
//   setPendingEscalation(event) / clearPendingEscalation()
//   setPendingContext(event)   / clearPendingContext()
//   setHumanEscalated(event)
//   setConnected(bool) / setReconnecting(bool)
//   setConfig(config)
//
// TODO(M1): messages KEEP the tier they were sent at. Do not re-style history on
//   escalation — the visible tier history is what makes the journey legible.
//
// TODO(M1): only one pending interrupt can be live at a time. Setting one must
//   clear the other; two open prompts means the UI and the paused graph have
//   diverged.

// TODO(M1): persist sessionId to localStorage so a refresh reconnects to the
//   same conversation rather than silently starting a new one.
