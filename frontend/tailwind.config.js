/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  // Use selector strategy to support our existing .dark-theme class
  darkMode: ['selector', '.dark-theme'],
  theme: {
    extend: {
      colors: {
        // Custom colors mapped from existing CSS variables
        background: {
          DEFAULT: '#f8fafc',
          dark: '#0f172a',
        },
        container: {
          DEFAULT: '#ffffff',
          dark: '#1e293b',
        },
        sidebar: {
          DEFAULT: '#ffffff',
          dark: '#334155',
        },
        text: {
          primary: '#0f172a',
          secondary: '#64748b',
          muted: '#94a3b8',
          'primary-dark': '#f8fafc',
          'secondary-dark': '#cbd5e1',
          'muted-dark': '#94a3b8',
        },
        primary: {
          DEFAULT: '#0066cc',
          hover: '#0052a3',
          light: '#e0f2fe',
          dark: '#3b82f6',
          'dark-hover': '#60a5fa',
        },
        secondary: {
          DEFAULT: '#6b7280',
          hover: '#4b5563',
          dark: '#94a3b8',
          'dark-hover': '#cbd5e1',
        },
        success: {
          DEFAULT: '#10b981',
          light: '#d1fae5',
          'dark-light': '#064e3b',
        },
        danger: {
          DEFAULT: '#ef4444',
          light: '#fee2e2',
          'dark-light': '#7f1d1d',
        },
        merge: {
          DEFAULT: '#16A34A',
          hover: '#15803D',
          ring: '#22C55E',
        },
        warning: {
          DEFAULT: '#f59e0b',
          light: '#fef3c7',
          'dark-light': '#78350f',
        },
        border: {
          DEFAULT: '#d1d5db',
          light: '#e5e7eb',
          dark: '#475569',
          'dark-light': '#64748b',
        },
        input: {
          bg: '#ffffff',
          border: '#cbd5e1',
          focus: '#0066cc',
          'dark-bg': '#1e293b',
          'dark-border': '#475569',
          'dark-focus': '#3b82f6',
        },
        hover: {
          bg: '#f1f5f9',
          'dark-bg': '#334155',
        },
      },
      spacing: {
        'xs': '0.25rem',
        'sm': '0.5rem',
        'md': '0.75rem',
        'lg': '1.5rem',
        'xl': '2rem',
        '2xl': '3rem',
      },
      borderRadius: {
        'sm': '0.375rem',
        'md': '0.5rem',
        'lg': '0.75rem',
        'xl': '1rem',
      },
      boxShadow: {
        'sm': '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
        'md': '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
        'lg': '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
        'xl': '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
        'dark-sm': '0 1px 2px 0 rgba(0, 0, 0, 0.2)',
        'dark-md': '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2)',
        'dark-lg': '0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.2)',
        'dark-xl': '0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 10px 10px -5px rgba(0, 0, 0, 0.3)',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'sans-serif'],
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [],
}

