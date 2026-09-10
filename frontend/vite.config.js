import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The build lands in frontend/dist/spa and is picked up by Django's
// collectstatic, because `frontend/dist` is added to STATICFILES_DIRS. That
// keeps every source file in this directory — nothing is written into the
// Django tree — while deployment stays exactly what it already is: run
// collectstatic. On cPanel that matters, because there is no opportunity to
// configure a second static root.
export default defineConfig({
  plugins: [react()],
  base: '/static/spa/',
  resolve: {
    alias: {
      // Absolute imports, so a component can be pulled in from anywhere
      // without counting `../` segments:  import { Button } from '@/ui'
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist/spa',
    emptyOutDir: true,
    // Django fingerprints nothing here; Vite's own content hashes are what
    // make a deploy cache-safe.
    assetsDir: 'assets',
    sourcemap: false,
    rollupOptions: {
      output: {
        // React changes far less often than the application does, so keeping
        // it in its own chunk means a routine deploy does not invalidate it.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
  server: {
    port: 5173,
    // Development only. The API is same-origin in production, and proxying in
    // development keeps it same-origin here too — which means no CORS
    // configuration exists to be got wrong, and the session cookie behaves
    // identically in both places.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/media': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
})
