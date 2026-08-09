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

// Contrast checked for `muted` on `bg` (the timestamps / tier-badge pairing) —
// each stays at or above WCAG AA (4.5:1) for normal text.
export const THEMES: Record<string, Theme> = {
  // Front Desk — neutral, unremarkable. You wouldn't look twice.
  slate: {
    bg: '#f8fafc',
    surface: '#ffffff',
    accent: '#475569',
    text: '#0f172a',
    muted: '#475569',
    avatarClass: 'bg-slate-200 text-slate-700',
  },
  // Department Manager — warmer, a little more considered.
  amber: {
    bg: '#fffbeb',
    surface: '#ffffff',
    accent: '#b45309',
    text: '#1c1917',
    muted: '#92400e',
    avatarClass: 'bg-amber-200 text-amber-900',
  },
  // Vice President — more saturated, more formal.
  indigo: {
    bg: '#eef2ff',
    surface: '#ffffff',
    accent: '#4338ca',
    text: '#1e1b4b',
    muted: '#4338ca',
    avatarClass: 'bg-indigo-200 text-indigo-900',
  },
  // Office of the CEO — the whole palette inverts. You've arrived somewhere
  // you were not expecting to end up.
  obsidian: {
    bg: '#0a0a0f',
    surface: '#16161f',
    accent: '#d4af37',
    text: '#f4f4f5',
    muted: '#a1a1aa',
    avatarClass: 'bg-[#d4af37]/20 text-[#d4af37]',
  },
};

export const FALLBACK_THEME = 'slate';

/** Returns THEMES[name] ?? THEMES[FALLBACK_THEME]. An unknown theme name from
 *  config degrades to the fallback rather than crashing the chat. */
export function getTheme(name: string): Theme {
  return THEMES[name] ?? THEMES[FALLBACK_THEME];
}

/** Writes the theme onto a root element as CSS custom properties, matching
 *  tailwind.config.js's `colors.tier.*`. */
export function applyTheme(el: HTMLElement, theme: Theme): void {
  el.style.setProperty('--tier-bg', theme.bg);
  el.style.setProperty('--tier-surface', theme.surface);
  el.style.setProperty('--tier-accent', theme.accent);
  el.style.setProperty('--tier-text', theme.text);
  el.style.setProperty('--tier-muted', theme.muted);
}

/** Display names for the tier badge. Distinct from persona names, which come
 *  from config — the badge is the rung, the name is the person. */
export const TIER_LABELS: Record<Tier, string> = {
  front_desk: 'Front Desk',
  manager: 'Department Manager',
  vice_president: 'Vice President',
  ceo: 'Office of the CEO',
};

export type { Tier };
