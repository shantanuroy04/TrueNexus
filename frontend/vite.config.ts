import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    // The page calls /api on its own origin; Vite forwards to the backend. 127.0.0.1, not
    // localhost: "localhost" can resolve to IPv6 ::1, where another program may own port 8000.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
    css: false,
    include: ['tests/**/*.test.tsx'],
    env: { VITE_API_BASE: 'http://localhost:8000' }, // tests mock this origin with MSW
  },
})
