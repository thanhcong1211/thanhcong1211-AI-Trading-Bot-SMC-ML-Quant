import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: '#0a0a0a',
          panel: '#111315',
          border: '#1f2a24',
          in: '#00ff41',
          out: '#ff3333',
          neutral: '#7a8a80',
          amber: '#ffb000'
        }
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Roboto Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace']
      },
      boxShadow: {
        'glow-in': '0 0 8px rgba(0, 255, 65, 0.45)',
        'glow-out': '0 0 8px rgba(255, 51, 51, 0.45)'
      }
    }
  },
  plugins: []
};

export default config;
