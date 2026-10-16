/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Brand palette (PrevaIQ navy scale); keep in sync with src/lib/brand.ts
        primary: {
          50: '#e8eef5',
          100: '#d1dde9',
          200: '#a3bbd3',
          300: '#7599bd',
          400: '#4777a7',
          500: '#2a5785',
          600: '#1f4770',
          700: '#17395C',
          800: '#0F2E4D',
          900: '#0a1f33',
        },
        brand: {
          primary: '#17395C',
          secondary: '#2EC4B6',
          accent: '#0F2E4D',
        },
        accent: {
          emerald: '#10b981',
          amber: '#f59e0b',
          rose: '#f43f5e',
          sky: '#0ea5e9',
          violet: '#8b5cf6',
          teal: '#14b8a6',
        },
      },
    },
  },
  plugins: [],
};
