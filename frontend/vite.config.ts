import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API_URL = process.env.VITE_API_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  build: {
    // video.js is a single ~700 kB monolith; axe-core is already lazy via
    // dynamic import in AxeScoreBadge. Neither can be split further.
    chunkSizeWarningLimit: 750,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom'],
          carbon: ['@carbon/react', '@carbon/icons-react'],
          video: ['video.js'],
          wavesurfer: ['wavesurfer.js'],
        },
      },
    },
  },
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
