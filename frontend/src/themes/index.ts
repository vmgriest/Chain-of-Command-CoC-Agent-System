/**
 * Per-tier visual identity.
 *
 * Theme names come from company_config.json (`personas.*.theme`), so a company
 * can re-skin the ladder without touching component code.
 *
 * Applied as CSS custom properties on a root wrapper — NOT by swapping Tailwind
 * classes. Custom properties transition smoothly; class swaps snap. The
 * escalation moment is the thing that sells the whole concept, so it animates.
 *
 * Design intent: the ladder gets visibly heavier and more formal as you climb.
 * Slate is neutral and unremarkable. Obsidian should feel like you have arrived
 * somewhere you were not expecting to end up.
 */

import type { Tier } from '@/types';

export interface Theme {
  bg: string;
  surface: string;
  accent: string;
  text: string;
  muted: string;
  /** Optional avatar/monogram treatment for the persona header. */
  avatarClass: string;
}

// TODO(M1): fill in real values. Placeholders below are structural only.
//   Check contrast — `muted` on `bg` is the pairing that usually fails WCAG AA,
//   and it is where timestamps and the tier badge live.
export const THEMES: Record<string, Theme> = {
  slate: {
    bg: '', surface: '', accent: '', text: '', muted: '', avatarClass: '',
  },
  amber: {
    bg: '', surface: '', accent: '', text: '', muted: '', avatarClass: '',
  },
  indigo: {
    bg: '', surface: '', accent: '', text: '', muted: '', avatarClass: '',
  },
  obsidian: {
    bg: '', surface: '', accent: '', text: '', muted: '', avatarClass: '',
  },
};

export const FALLBACK_THEME = 'slate';

/** TODO(M1): return THEMES[name] ?? THEMES[FALLBACK_THEME].
 *  An unknown theme name from config must degrade, not crash the chat. */
export function getTheme(_name: string): Theme {
  throw new Error('not implemented');
}

/** TODO(M1): write the theme onto a root element as CSS custom properties
 *  (--tier-bg, --tier-surface, ...), matching tailwind.config.js. */
export function applyTheme(_el: HTMLElement, _theme: Theme): void {
  throw new Error('not implemented');
}

// TODO(M1): TIER_LABELS — display names for the tier badge
//   ("Front Desk", "Department Manager", "Vice President", "Office of the CEO").
//   Distinct from persona names, which come from config.

export type { Tier };
