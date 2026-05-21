import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        cod: {
          navy: '#003087',
          gold: '#B59B2C',
          'gold-light': '#F0D060',
          'navy-dark': '#001f5b',
          'navy-light': '#0045b5',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;
