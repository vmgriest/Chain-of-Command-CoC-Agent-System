/**
 * Escalation consent prompt — the human-in-the-loop gate.
 *
 * ⚠ INLINE in the chat flow, NOT a modal. A modal frames escalation as an
 *   interruption to dismiss. Inline frames it as part of the conversation, which
 *   is what it is.
 *
 * Only appears for AGENT-initiated escalation. A customer who asked for a
 * manager is never asked to confirm.
 */

import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

import type { EscalationPromptEvent } from '@/types';

interface EscalationPromptProps {
  event: EscalationPromptEvent;
  onRespond: (approved: boolean) => void;
}

export function EscalationPrompt({ event, onRespond }: EscalationPromptProps): JSX.Element {
  const yesRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    yesRef.current?.focus();
  }, []);

  return (
    <motion.div
      role="group"
      aria-label="Escalation request"
      className="theme-surface mx-4 my-2 rounded-xl border p-4"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <p className="text-sm">{event.question}</p>
      <p className="theme-muted mt-1 text-xs">
        You'd be transferred to {event.to_persona}, {event.to_title}.
      </p>
      <div className="mt-3 flex gap-2">
        <button
          ref={yesRef}
          type="button"
          onClick={() => onRespond(true)}
          className="theme-accent rounded-lg border px-3 py-1.5 text-sm font-medium hover:opacity-80"
        >
          Yes, bring them in
        </button>
        <button
          type="button"
          onClick={() => onRespond(false)}
          className="rounded-lg border px-3 py-1.5 text-sm font-medium opacity-80 hover:opacity-100"
        >
          No, keep trying here
        </button>
      </div>
    </motion.div>
  );
}
