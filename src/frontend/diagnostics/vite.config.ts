import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // not Vite's default 5173, so another Vite app on this machine keeps its port
    port: 5174,
    // the API runs as `python -m backend.diagnostics`; the build is served by that same process instead
    proxy: { '/api': 'http://127.0.0.1:8001' },
  },
  build: {
    // the licence notices of every package the build bundles, written by Vite itself with each build, so they list
    // exactly what dist/ ships and cannot fall out of step with it
    license: { fileName: 'THIRD_PARTY_NOTICES.md' },
  },
})
