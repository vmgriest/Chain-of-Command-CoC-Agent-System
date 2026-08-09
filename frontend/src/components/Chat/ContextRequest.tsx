/**
 * Context request — the agent needs a specific fact to continue.
 *
 * ⚠ INLINE, not a modal. Same reasoning as EscalationPrompt.
 *
 * ⚠ CONDITIONAL. This appears only when the agent genuinely needs something. Most
 *   turns render nothing here. If it starts showing up every turn, the backend's
 *   needs_context logic has regressed into a per-turn checkpoint.
 */

import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';

import type { ContextRequestEvent } from '@/types';

interface ContextRequestProps {
  event: ContextRequestEvent;
  onSubmit: (answer: string) => void;
}

export function ContextRequest({ event, onSubmit }: ContextRequestProps): JSX.Element {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const submit = (answer: string): void => {
    onSubmit(answer);
    setValue('');
  };

  return (
    <motion.div
      role="group"
      aria-label="Information needed"
      className="theme-surface mx-4 my-2 rounded-xl border p-4"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <p className="text-sm">{event.question}</p>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit(value);
        }}
      >
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Type your answer…"
          className="theme-surface flex-1 rounded-lg border px-3 py-1.5 text-sm outline-none"
        />
        <button
          type="submit"
          disabled={!value.trim()}
          className="theme-accent rounded-lg border px-3 py-1.5 text-sm font-medium hover:opacity-80 disabled:opacity-40"
        >
          Send
        </button>
      </form>
      {/* A customer who won't share the detail should not be stuck — declining
          lets the agent work around it or escalate, rather than blocking. */}
      <button
        type="button"
        onClick={() => submit("I'd rather not say")}
        className="theme-muted mt-2 text-xs underline"
      >
        I'd rather not say
      </button>
    </motion.div>
  );
}
