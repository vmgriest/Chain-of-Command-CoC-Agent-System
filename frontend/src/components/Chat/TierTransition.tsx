/**
 * The escalation divider — the visual centerpiece.
 *
 * Rendered inline in the message list when a tier_change arrives, and it STAYS
 * in scrollback. The conversation becomes a visible record of the journey up the
 * ladder rather than a flat transcript that mysteriously changes color.
 */

import { motion } from 'framer-motion';

import { getTheme, TIER_LABELS } from '@/themes';
import type { TierChangeEvent } from '@/types';

export function TierTransition({ event }: { event: TierChangeEvent }): JSX.Element {
  const toTheme = getTheme(event.theme);

  return (
    <motion.div
      className="my-4 flex flex-col items-center gap-2 px-4 text-center"
      initial={{ opacity: 0, scaleX: 0.7 }}
      animate={{ opacity: 1, scaleX: 1 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
    >
      <div className="flex w-full items-center gap-3">
        <span className="h-px flex-1" style={{ backgroundColor: toTheme.accent, opacity: 0.4 }} />
        <span
          className="whitespace-nowrap rounded-full border px-3 py-1 text-xs font-medium"
          style={{ borderColor: toTheme.accent, color: toTheme.accent }}
        >
          {event.from_persona} ({TIER_LABELS[event.from_tier]}) → {event.to_persona} (
          {TIER_LABELS[event.to_tier]})
        </span>
        <span className="h-px flex-1" style={{ backgroundColor: toTheme.accent, opacity: 0.4 }} />
      </div>

      <motion.p
        className="theme-muted max-w-md text-xs italic"
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.15 }}
      >
        {event.reason}
      </motion.p>

      {/* packet_summary is the payoff of the whole handoff protocol — showing
          exactly what carried forward is what distinguishes this from a phone
          tree that makes the customer repeat themselves, so it gets top billing
          rather than a footnote. */}
      <motion.p
        className="theme-surface max-w-md rounded-lg border px-3 py-2 text-sm font-medium"
        style={{ borderColor: toTheme.accent }}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.25 }}
      >
        {event.packet_summary}
      </motion.p>
    </motion.div>
  );
}
