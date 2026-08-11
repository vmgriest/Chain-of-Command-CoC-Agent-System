/**
 * Escalation transitions: theme swap and animation sequencing.
 *
 * This is the moment that sells the whole concept — the customer must be certain
 * they moved up, not stalled. It gets more care than a theme swap normally would.
 */

import { useEffect, useRef, useState } from 'react';

import { useChatStore } from '@/store/chat';
import { getTheme } from '@/themes';
import type { Theme } from '@/themes';
import type { ClientEvent, Tier } from '@/types';

const TRANSITION_MS = 800;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  );
}

/** Tracks the escalation transition: theme swap and animation sequencing.
 *
 * On a tier_change event (reflected here as currentTier changing in the
 * store), `transitioning` flips true for ~800ms so the UI can fade the old
 * header, animate in the TierTransition divider, and cross-fade the themed
 * surfaces before settling on the new tier — long enough to register as an
 * event, short enough not to feel like the app hung. `theme` updates
 * immediately (CSS custom properties transition on their own via
 * --tier-transition-ms), so the color shift and the "transitioning" flag are
 * independent: components block input on the flag, not on the color.
 *
 * `send` is threaded in from useWebSocket so respondToEscalation can resume
 * the paused graph directly.
 */
export function useEscalation(send: (event: ClientEvent) => void): {
  currentTier: Tier;
  theme: Theme;
  transitioning: boolean;
  respondToEscalation: (approved: boolean) => void;
} {
  const currentTier = useChatStore((s) => s.currentTier);
  const clearPendingEscalation = useChatStore((s) => s.clearPendingEscalation);
  const [transitioning, setTransitioning] = useState(false);
  // useRef, not useState, for these two: changing them must NOT trigger a
  // re-render (they're bookkeeping for the effect below, not something drawn
  // on screen), and a ref's value survives across renders without resetting,
  // unlike a plain local variable would.
  const previousTierRef = useRef(currentTier);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (previousTierRef.current === currentTier) {
      return;
    }
    previousTierRef.current = currentTier;

    if (prefersReducedMotion()) {
      // The divider and theme change still render; only the motion is
      // optional, so there is nothing to time here.
      return;
    }

    setTransitioning(true);
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => setTransitioning(false), TRANSITION_MS);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [currentTier]);

  const respondToEscalation = (approved: boolean): void => {
    send({ type: 'escalation_response', approved });
    clearPendingEscalation();
  };

  const config = useChatStore((s) => s.config);
  const themeName = config?.personas[currentTier]?.theme ?? 'slate';

  return {
    currentTier,
    theme: getTheme(themeName),
    transitioning,
    respondToEscalation,
  };
}
