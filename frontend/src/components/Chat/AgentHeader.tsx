/**
 * Persona header — who you are currently talking to.
 *
 * Shows the persona's real name from config plus the tier badge. The name is the
 * company's ("Jensen Huang"), the badge is the rung ("Office of the CEO"); both
 * matter and they are not the same thing.
 */

import { AnimatePresence, motion } from 'framer-motion';

import { useChatStore } from '@/store/chat';
import { TIER_LABELS, type Theme } from '@/themes';
import { TIER_ORDER } from '@/types';

interface AgentHeaderProps {
  theme: Theme;
  transitioning: boolean;
  connected: boolean;
  reconnecting: boolean;
}

export function AgentHeader({
  theme,
  transitioning,
  connected,
  reconnecting,
}: AgentHeaderProps): JSX.Element {
  const currentTier = useChatStore((s) => s.currentTier);
  const currentPersona = useChatStore((s) => s.currentPersona);
  const config = useChatStore((s) => s.config);

  const persona = config?.personas[currentTier];
  const displayName = currentPersona || persona?.name || '';
  const title = persona?.title ?? '';
  const initial = displayName ? displayName[0] : '?';
  const position = TIER_ORDER.indexOf(currentTier);

  return (
    <header className="theme-surface flex items-center justify-between gap-3 border-b px-4 py-3">
      <div className="flex items-center gap-3">
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold ${theme.avatarClass}`}
        >
          {initial}
        </div>
        <AnimatePresence mode="wait">
          {/* The header must not swap before the tier_change divider lands —
              gating on `transitioning` (owned by useEscalation) keeps them in
              step rather than racing on independent state. */}
          {!transitioning && (
            <motion.div
              key={currentTier}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.25 }}
            >
              <div className="font-semibold leading-tight">{displayName}</div>
              <div className="theme-muted text-xs leading-tight">{title}</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="flex items-center gap-3">
        {/* Four small dots, one per tier — filled up to the current position,
            hollow beyond it. A compact "how far up the ladder are we" readout
            that doesn't require reading the tier badge text. aria-hidden
            because the badge text below already conveys the same information
            to a screen reader. */}
        <div className="hidden items-center gap-1 sm:flex" aria-hidden="true">
          {TIER_ORDER.map((tier, i) => (
            <span
              key={tier}
              className="h-1.5 w-1.5 rounded-full"
              style={{
                backgroundColor: i <= position ? theme.accent : 'transparent',
                border: `1px solid ${theme.accent}`,
                opacity: i <= position ? 1 : 0.4,
              }}
            />
          ))}
        </div>
        <span
          className="theme-accent rounded-full border px-2 py-0.5 text-xs font-medium"
          style={{ borderColor: theme.accent }}
        >
          {TIER_LABELS[currentTier]}
        </span>
        {reconnecting ? (
          <span className="text-xs text-amber-600" role="status">
            Reconnecting…
          </span>
        ) : !connected ? (
          <span className="text-xs text-red-600" role="status">
            Offline
          </span>
        ) : null}
      </div>
    </header>
  );
}
