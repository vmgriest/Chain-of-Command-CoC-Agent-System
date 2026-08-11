/**
 * Message composer.
 */

import { useEffect, useRef, useState } from 'react';

import { useChatStore } from '@/store/chat';
import type { ClientEvent } from '@/types';

const MAX_HEIGHT_PX = 160;

interface MessageInputProps {
  send: (event: ClientEvent) => void;
  transitioning: boolean;
  connected: boolean;
}

export function MessageInput({ send, transitioning, connected }: MessageInputProps): JSX.Element {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const appendUserMessage = useChatStore((s) => s.appendUserMessage);
  const startAgentMessage = useChatStore((s) => s.startAgentMessage);
  const currentTier = useChatStore((s) => s.currentTier);
  const pendingEscalation = useChatStore((s) => s.pendingEscalation);
  const pendingContext = useChatStore((s) => s.pendingContext);
  const turnInProgress = useChatStore((s) => s.turnInProgress);

  const hasPendingPrompt = Boolean(pendingEscalation || pendingContext);

  // Each disabled reason gets its own copy — a generically disabled input with
  // no explanation reads as a broken app.
  let placeholder = 'Type a message…';
  if (transitioning) {
    placeholder = 'Connecting you now…';
  } else if (hasPendingPrompt) {
    placeholder = 'Please answer above first…';
  } else if (turnInProgress) {
    // Waiting on the current turn rather than blocked on the user — a second
    // message sent here would arrive mid-stream and get its tokens tangled
    // with the reply still in flight.
    placeholder = 'Waiting for a response…';
  } else if (!connected) {
    placeholder = "You're offline — reconnecting…";
  }

  const disabled = transitioning || hasPendingPrompt || turnInProgress;

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  // Keep focus after send, and once a tier transition completes.
  useEffect(() => {
    if (!disabled) {
      textareaRef.current?.focus();
    }
  }, [disabled]);

  const submit = (): void => {
    const content = value.trim();
    if (!content || disabled) return;
    // Optimistic UI: the user's bubble and an empty "typing" agent bubble
    // both appear immediately, before the server has even received the
    // message — appendToken() (frontend/src/store/chat.ts) then fills that
    // agent bubble in as real tokens stream back over the WebSocket.
    appendUserMessage(content);
    startAgentMessage(currentTier);
    send({ type: 'user_message', content });
    setValue('');
    textareaRef.current?.focus();
  };

  return (
    <div className="theme-surface flex items-end gap-2 border-t p-3">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        disabled={disabled}
        placeholder={placeholder}
        rows={1}
        className="flex-1 resize-none rounded-xl border bg-transparent px-3 py-2 text-sm outline-none disabled:opacity-50"
      />
      <button
        type="button"
        onClick={submit}
        disabled={disabled || !value.trim()}
        className="theme-accent rounded-xl border px-4 py-2 text-sm font-medium hover:opacity-80 disabled:opacity-40"
      >
        Send
      </button>
    </div>
  );
}
