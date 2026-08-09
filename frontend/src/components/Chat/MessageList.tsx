/**
 * Scrollback. Renders messages plus inline TierTransition markers.
 */

import { useEffect, useRef } from 'react';

import { useChatStore } from '@/store/chat';
import { getTheme } from '@/themes';

import { TierTransition } from './TierTransition';

const NEAR_BOTTOM_PX = 120;

export function MessageList(): JSX.Element {
  const timeline = useChatStore((s) => s.timeline);
  const config = useChatStore((s) => s.config);
  const containerRef = useRef<HTMLDivElement>(null);
  const wasNearBottomRef = useRef(true);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      wasNearBottomRef.current =
        el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    };
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  // Auto-scroll on new content, but only when the user was already near the
  // bottom — yanking the view while someone reads scrollback is a small
  // betrayal.
  useEffect(() => {
    const el = containerRef.current;
    if (el && wasNearBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [timeline]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-2 py-3"
      aria-live="polite"
      aria-relevant="additions"
    >
      {timeline.map((item) => {
        if (item.kind === 'transition') {
          return (
            <div key={item.id}>
              {/* A purely visual theme swap conveys nothing to a screen reader
                  user, so the handoff gets an explicit text announcement too. */}
              <span className="sr-only" role="status">
                Escalated from {item.event.from_persona} to {item.event.to_persona}.{' '}
                {item.event.packet_summary}
              </span>
              <TierTransition event={item.event} />
            </div>
          );
        }

        // An agent bubble opened in anticipation of a reply that turned out to
        // be a silent interrupt (e.g. the model asked for context before
        // saying anything) has nothing to show — skip it rather than render
        // an empty box.
        if (item.role === 'agent' && !item.content && !item.streaming) {
          return null;
        }

        const messageTheme = getTheme(
          item.role === 'agent' ? (config?.personas[item.tier]?.theme ?? 'slate') : 'slate'
        );
        const isUser = item.role === 'user';

        return (
          <div key={item.id} className={`my-1.5 flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm ${isUser ? 'text-white' : ''}`}
              style={
                isUser
                  ? { backgroundColor: 'var(--tier-accent)' }
                  : { backgroundColor: messageTheme.surface, color: messageTheme.text, border: `1px solid ${messageTheme.accent}22` }
              }
            >
              {!isUser && item.personaName && (
                <div className="mb-0.5 text-xs font-semibold opacity-70">{item.personaName}</div>
              )}
              <span>
                {item.content}
                {item.streaming && <span className="ml-0.5 animate-pulse">▍</span>}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
