/**
 * Root chat shell. Owns the theme wrapper and lays out header / messages /
 * input / pending prompts.
 */

import { useEffect, useRef } from 'react';

import { useWebSocket } from '@/hooks/useWebSocket';
import { useEscalation } from '@/hooks/useEscalation';
import { useChatStore } from '@/store/chat';
import { applyTheme } from '@/themes';

import { AgentHeader } from './AgentHeader';
import { ContextRequest } from './ContextRequest';
import { EscalationPrompt } from './EscalationPrompt';
import { HumanEscalationBanner } from './HumanEscalationBanner';
import { MessageInput } from './MessageInput';
import { MessageList } from './MessageList';

export function ChatContainer(): JSX.Element {
  const sessionId = useChatStore((s) => s.sessionId);
  const { send, connected, reconnecting } = useWebSocket(sessionId);
  const { theme, transitioning, respondToEscalation } = useEscalation(send);

  const pendingEscalation = useChatStore((s) => s.pendingEscalation);
  const pendingContext = useChatStore((s) => s.pendingContext);
  const humanEscalated = useChatStore((s) => s.humanEscalated);
  const humanEscalationMessage = useChatStore((s) => s.humanEscalationMessage);
  const schedulingLink = useChatStore((s) => s.schedulingLink);

  const themeRootRef = useRef<HTMLDivElement>(null);

  // Re-applies the CSS custom properties (--tier-bg, --tier-accent, etc.) onto
  // the root div every time `theme` changes. Everything downstream (bubbles,
  // buttons, the accent color) reads those variables in its own CSS rather
  // than being handed a color directly — see frontend/src/themes/index.ts for
  // why that's what makes the color shift animate instead of snap.
  useEffect(() => {
    if (themeRootRef.current) {
      applyTheme(themeRootRef.current, theme);
    }
  }, [theme]);

  const respondToContext = (answer: string): void => {
    send({ type: 'context_response', answer });
    useChatStore.getState().clearPendingContext();
  };

  return (
    <div ref={themeRootRef} className="theme-root flex h-screen flex-col">
      <AgentHeader
        theme={theme}
        transitioning={transitioning}
        connected={connected}
        reconnecting={reconnecting}
      />
      <MessageList />

      {/* At most ONE pending prompt renders at a time — two open prompts would
          mean the UI and the paused graph have diverged. The store already
          enforces this (setPendingEscalation/setPendingContext clear each
          other), so checking escalation before context here is just ordering,
          not a race. */}
      {pendingEscalation && (
        <EscalationPrompt event={pendingEscalation} onRespond={respondToEscalation} />
      )}
      {!pendingEscalation && pendingContext && (
        <ContextRequest event={pendingContext} onSubmit={respondToContext} />
      )}

      {/* Sticky but non-blocking: the chat stays fully usable underneath this.
          Disabling input once a human is looped in is exactly what must NOT
          happen here. */}
      {humanEscalated && (
        <HumanEscalationBanner
          message={humanEscalationMessage ?? 'A member of our team has been notified.'}
          schedulingLink={schedulingLink}
        />
      )}

      <MessageInput send={send} transitioning={transitioning} connected={connected} />
    </div>
  );
}
