import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/config': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/sources': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/rules': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/history': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/scheduler': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/users': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
})
