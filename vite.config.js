import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy API calls to FastAPI during local dev
    // so you never need to worry about CORS in development
    proxy: {
      '/vouchers': 'http://localhost:8000',
      '/chat':     'http://localhost:8000',
      '/health':   'http://localhost:8000',
      '/merchants':'http://localhost:8000',
    },
  },
})
