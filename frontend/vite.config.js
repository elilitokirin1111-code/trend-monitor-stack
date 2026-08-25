import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'url'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

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
        target: apiProxyTarget,
        changeOrigin: true
      },
      '/auth': {
        target: apiProxyTarget,
        changeOrigin: true
      },
      '/config': {
        target: apiProxyTarget,
        changeOrigin: true
      },
      '/sources': {
        target: apiProxyTarget,
        changeOrigin: true
      },
      '/rules': {
        target: apiProxyTarget,
        changeOrigin: true
      },
      '/history': {
        target: apiProxyTarget,
        changeOrigin: true
      },
      '/scheduler': {
        target: apiProxyTarget,
        changeOrigin: true
      },
      '/users': {
        target: apiProxyTarget,
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
})
