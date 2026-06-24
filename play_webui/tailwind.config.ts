import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#09090b',
        foreground: '#f8fafc',
        panel: '#111827',
        muted: '#94a3b8',
        accent: '#a855f7',
      },
    },
  },
  plugins: [],
}

export default config
