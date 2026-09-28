import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend origin for the dev proxy. Override with SATSA_API when the backend
// runs on a different local port; production is served behind nginx instead.
const API_TARGET = process.env.SATSA_API || 'http://127.0.0.1:8000'

// No CDNs, no remote fonts: everything the browser loads is bundled from
// node_modules at build time.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
})
