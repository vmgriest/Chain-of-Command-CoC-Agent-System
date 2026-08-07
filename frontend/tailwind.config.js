/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // Per-tier theming is driven by CSS custom properties set on a root
      // wrapper (see src/themes/index.ts), NOT by swapping Tailwind classes.
      // Custom properties transition smoothly; class swaps snap. The escalation
      // moment is the whole demo, so it needs to animate.
      colors: {
        tier: {
          bg: 'var(--tier-bg)',
          surface: 'var(--tier-surface)',
          accent: 'var(--tier-accent)',
          text: 'var(--tier-text)',
          muted: 'var(--tier-muted)',
        },
      },
      transitionProperty: {
        theme: 'background-color, border-color, color',
      },
    },
  },
  plugins: [],
};
