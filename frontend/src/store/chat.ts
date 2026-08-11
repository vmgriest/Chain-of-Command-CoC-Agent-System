/**
 * Chat state (Zustand).
 *
 * Single source of truth for messages, the current tier, and any pending
 * interrupt. The WS hook dispatches into this; components only read.
 */

import { create } from 'zustand';

import { newSessionId } from '@/lib/api';
import type {
  ChatMessage,
  ContextRequestEvent,
  EscalationPromptEvent,
  HumanEscalationEvent,
  PublicConfig,
  Tier,
  TierChangeEvent,
} from '@/types';

/** A tier-transition marker rendered inline in the message list. Distinct from
 *  ChatMessage so MessageList can special-case its rendering (TierTransition). */
export interface TransitionMarker {
  id: string;
  kind: 'transition';
  event: TierChangeEvent;
}

export type Timelined = ChatMessage | TransitionMarker;

export interface ChatState {
  // --- connection ---
  sessionId: string;
  connected: boolean;
  reconnecting: boolean;

  // --- conversation ---
  timeline: Timelined[];
  currentTier: Tier;
  currentPersona: string;
  // True from the moment a client event is sent until the server's turn_end.
  // Gates the composer so a second message can't be sent mid-turn — without
  // this, tokens from the in-flight turn keep arriving after a new message
  // starts a new bubble, and get appended to the wrong one.
  turnInProgress: boolean;

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

  // --- actions ---
  appendUserMessage: (content: string) => void;
  startAgentMessage: (tier: Tier, personaName?: string) => void;
  appendToken: (content: string) => void;
  finishAgentMessage: () => void;
  handleTierChange: (event: TierChangeEvent) => void;
  setPendingEscalation: (event: EscalationPromptEvent) => void;
  clearPendingEscalation: () => void;
  setPendingContext: (event: ContextRequestEvent) => void;
  clearPendingContext: () => void;
  setHumanEscalated: (event: HumanEscalationEvent) => void;
  setConnected: (connected: boolean) => void;
  setReconnecting: (reconnecting: boolean) => void;
  setConfig: (config: PublicConfig) => void;
  setTurnInProgress: (inProgress: boolean) => void;
}

let idCounter = 0;
function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-${idCounter}-${Date.now()}`;
}

// create() returns a hook: any component calling useChatStore(selector) both
// reads the selected slice of state AND automatically re-renders whenever
// that specific slice changes — no <Provider> wrapper, no manual
// subscription. `set` merges a partial update into state (like React's
// setState); `get` reads the current state from inside an action, used below
// wherever an action needs to see state that isn't in its own arguments.
export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: newSessionId(),
  connected: false,
  reconnecting: false,

  timeline: [],
  currentTier: 'front_desk',
  currentPersona: '',
  turnInProgress: false,

  pendingEscalation: null,
  pendingContext: null,

  humanEscalated: false,
  humanEscalationMessage: null,
  schedulingLink: null,

  config: null,

  appendUserMessage: (content) => {
    const message: ChatMessage = {
      id: nextId('user'),
      kind: 'message',
      role: 'user',
      content,
      tier: get().currentTier,
    };
    set((state) => ({ timeline: [...state.timeline, message] }));
  },

  startAgentMessage: (tier, personaName) => {
    const message: ChatMessage = {
      id: nextId('agent'),
      kind: 'message',
      role: 'agent',
      content: '',
      tier,
      personaName,
      streaming: true,
    };
    set((state) => ({ timeline: [...state.timeline, message] }));
  },

  appendToken: (content) => {
    set((state) => {
      const timeline = [...state.timeline];
      for (let i = timeline.length - 1; i >= 0; i -= 1) {
        const item = timeline[i];
        if (item.kind === 'message' && item.role === 'agent' && item.streaming) {
          timeline[i] = { ...item, content: item.content + content };
          return { timeline };
        }
      }
      // No open agent message yet (e.g. a node emitted text without an explicit
      // start, such as the CEO's human-escalation notice) — start one.
      timeline.push({
        id: nextId('agent'),
        kind: 'message',
        role: 'agent',
        content,
        tier: state.currentTier,
        streaming: true,
      });
      return { timeline };
    });
  },

  finishAgentMessage: () => {
    set((state) => {
      const timeline = [...state.timeline];
      for (let i = timeline.length - 1; i >= 0; i -= 1) {
        const item = timeline[i];
        if (item.kind === 'message' && item.role === 'agent' && item.streaming) {
          timeline[i] = { ...item, streaming: false };
          break;
        }
      }
      return { timeline };
    });
  },

  // Messages KEEP the tier they were sent at — do not re-style history on
  // escalation. The visible tier history is what makes the journey legible.
  handleTierChange: (event) => {
    const marker: TransitionMarker = { id: nextId('transition'), kind: 'transition', event };
    set((state) => ({
      timeline: [...state.timeline, marker],
      currentTier: event.to_tier,
      currentPersona: event.to_persona,
    }));
  },

  // Only one pending interrupt can be live at a time — setting one clears the
  // other, since two open prompts would mean the UI and the paused graph have
  // diverged.
  setPendingEscalation: (event) => set({ pendingEscalation: event, pendingContext: null }),
  clearPendingEscalation: () => set({ pendingEscalation: null }),
  setPendingContext: (event) => set({ pendingContext: event, pendingEscalation: null }),
  clearPendingContext: () => set({ pendingContext: null }),

  setHumanEscalated: (event) =>
    set({
      humanEscalated: true,
      humanEscalationMessage: event.message,
      schedulingLink: event.scheduling_link,
    }),

  setConnected: (connected) => set({ connected }),
  setReconnecting: (reconnecting) => set({ reconnecting }),
  setConfig: (config) => set({ config }),
  setTurnInProgress: (inProgress) => set({ turnInProgress: inProgress }),
}));
