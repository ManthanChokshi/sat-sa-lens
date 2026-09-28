/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        navy: {
          950: '#08152b',
          900: '#0f2545',
          800: '#16345e',
          700: '#1e4478',
          600: '#2a568f',
        },
        accent: {
          50: '#eef5ff',
          100: '#d9e8ff',
          300: '#8cbaff',
          500: '#1f6feb',
          600: '#1659c4',
          700: '#12489e',
        },
        risk: {
          high: '#b91c1c',
          highbg: '#fef2f2',
          medium: '#b45309',
          mediumbg: '#fffbeb',
          low: '#15803d',
          lowbg: '#f0fdf4',
        },
        ink: {
          900: '#111827',
          700: '#374151',
          500: '#6b7280',
          300: '#d1d5db',
          100: '#f3f4f6',
          50: '#f9fafb',
        },
      },
      boxShadow: {
        card: '0 1px 2px rgba(16,24,40,0.05), 0 1px 3px rgba(16,24,40,0.06)',
      },
    },
  },
  plugins: [],
}
