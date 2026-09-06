import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/departments': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/coa': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/voice-tester': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/emergency': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/optimize': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/reoptimize': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/shadow': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
})
