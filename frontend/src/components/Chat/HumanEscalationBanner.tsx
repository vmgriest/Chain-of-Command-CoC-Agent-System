/**
 * Status banner shown after the CEO involves a human.
 *
 * ⚠ THE CHAT CONTINUES UNDERNEATH THIS. The banner is informational — it is not
 *   a terminal state, and the input must stay enabled. The intuitive
 *   implementation is to disable the composer once a human is looped in; that is
 *   exactly what must not happen.
 */

import { useState } from 'react';
import { motion } from 'framer-motion';

interface HumanEscalationBannerProps {
  message: string;
  schedulingLink: string | null;
}

export function HumanEscalationBanner({
  message,
  schedulingLink,
}: HumanEscalationBannerProps): JSX.Element {
  const [dismissed, setDismissed] = useState(false);

  // Dismissible to a compact pill — it should not consume vertical space for
  // the rest of the conversation, but stays visible as a reminder.
  if (dismissed) {
    return (
      <button
        type="button"
        onClick={() => setDismissed(false)}
        className="theme-accent mx-4 my-2 rounded-full border px-3 py-1 text-xs font-medium"
      >
        A team member has been notified ▾
      </button>
    );
  }

  return (
    <motion.div
      role="status"
      className="theme-surface mx-4 my-2 rounded-xl border-l-4 p-4"
      style={{ borderLeftColor: 'var(--tier-accent)' }}
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm">{message}</p>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Collapse"
          className="theme-muted text-xs"
        >
          ✕
        </button>
      </div>
      {schedulingLink && (
        <a
          href={schedulingLink}
          target="_blank"
          rel="noreferrer"
          className="theme-accent mt-2 inline-block text-sm underline"
        >
          Or schedule a call directly
        </a>
      )}
      <p className="theme-muted mt-1 text-xs">
        I'm still right here — feel free to keep asking questions in the meantime.
      </p>
    </motion.div>
  );
}
