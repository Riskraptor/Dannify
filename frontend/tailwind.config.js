// Colors are driven by CSS custom properties (see src/index.css) so the
// whole app re-themes by flipping [data-theme] on <html>. Each variable
// holds space-separated RGB channels, which keeps Tailwind's opacity
// modifiers working (e.g. `bg-tint/5`, `text-fg/60`).
const rgbVar = (name) => `rgb(var(${name}) / <alpha-value>)`

module.exports = {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        app: rgbVar('--c-app'), // window chrome (title bar, player bar)
        panel: rgbVar('--c-panel'), // sidebar / main / side panels
        raised: rgbVar('--c-raised'), // cards & inputs inside a panel
        elev: rgbVar('--c-elev'), // menus, dialogs, toasts
        fg: rgbVar('--c-fg'), // text
        tint: rgbVar('--c-tint'), // neutral overlay (white on dark, black on light)
        accent: rgbVar('--c-accent'),
        'accent-fg': rgbVar('--c-accent-fg'),
        danger: rgbVar('--c-danger'),
        warn: rgbVar('--c-warn'),
        dannify: {
          50: '#e6fbf0',
          100: '#c5f4d8',
          200: '#88e9b1',
          300: '#48dd87',
          400: '#1ad05c',
          500: '#15b150',
          600: '#10913f',
          700: '#0d6f31',
          800: '#0a4d22',
          900: '#062c14',
        },
      },
      fontFamily: {
        sans: [
          '"Segoe UI Variable Text"',
          '"Segoe UI"',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Helvetica Neue"',
          'Arial',
          'sans-serif',
        ],
        display: [
          '"Segoe UI Variable Display"',
          '"Segoe UI"',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Helvetica Neue"',
          'Arial',
          'sans-serif',
        ],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      boxShadow: {
        pop: 'var(--shadow-pop)',
        card: 'var(--shadow-card)',
        'glow-sm': '0 0 24px rgba(26, 208, 92, 0.18)',
        glow: '0 0 36px rgba(26, 208, 92, 0.30)',
      },
      transitionTimingFunction: {
        out: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.32s cubic-bezier(0.16, 1, 0.3, 1)',
        'pulse-soft': 'pulseSoft 2.4s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: 0 },
          '100%': { opacity: 1 },
        },
        slideUp: {
          '0%': { opacity: 0, transform: 'translateY(10px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: 0.7 },
          '50%': { opacity: 1 },
        },
        eq: {
          '0%, 100%': { transform: 'scaleY(0.35)' },
          '50%': { transform: 'scaleY(1)' },
        },
      },
    },
  },
  plugins: [],
}
