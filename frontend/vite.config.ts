import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API_URL = process.env.VITE_API_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/check':      { target: API_URL, changeOrigin: true },
      '/gaps':       { target: API_URL, changeOrigin: true },
      '/fix':        { target: API_URL, changeOrigin: true },
      '/report':     { target: API_URL, changeOrigin: true },
      '/health':     { target: API_URL, changeOrigin: true },
      '/live':       { target: API_URL.replace('http', 'ws'), ws: true },
    },
  },
})
