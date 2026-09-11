import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The build lands in frontend/dist/spa and is picked up by Django's
// collectstatic, because `frontend/dist` is added to STATICFILES_DIRS. That
// keeps every source file in this directory — nothing is written into the
// Django tree — while deployment stays exactly what it already is: run
// collectstatic. On cPanel that matters, because there is no opportunity to
// configure a second static root.
//
// Every server address comes from one variable, VITE_BASE_URL (.env.example).
// src/lib/config.js is its only reader in the application.
export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, fileURLToPath(new URL('.', import.meta.url)), 'VITE_')
  const backend = (env.VITE_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')
  const appBase = `${(env.VITE_APP_BASENAME || '/app').replace(/\/+$/, '')}/`

  // What the browser uses. In development it is empty on purpose: requests go
  // to the dev server, which proxies them to `backend`, so they stay
  // same-origin and the session cookie and CSRF token keep working without
  // CORS. In a build it is VITE_BASE_URL as given — empty (the default) when
  // Django serves the page itself.
  const serverUrl = command === 'build' ? (env.VITE_BASE_URL || '').replace(/\/+$/, '') : ''

  return {
    plugins: [
      react(),
      {
        // index.html cannot import config.js, so its server paths (the Cairo
        // font) are written as %SERVER_URL%/static/... and filled in here.
        name: 'server-url-in-html',
        // 'pre': before Vite reads the tags, which it cannot do with a raw %.
        transformIndexHtml: {
          order: 'pre',
          handler: (html) => html.replaceAll('%SERVER_URL%', serverUrl),
        },
      },
    ],
    define: {
      'import.meta.env.VITE_SERVER_URL': JSON.stringify(serverUrl),
    },
    // The build is served from Django's static tree, but the dev server has to
    // answer at the router's own prefix — otherwise the page opens at
    // /static/spa/ and the router, mounted at /app, renders nothing.
    base: command === 'build' ? `${serverUrl}/static/spa/` : appBase,
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
      // Development only. Everything outside the app's own prefix — /api,
      // /media, /static, and the Django pages the app links to (exports,
      // prescription print) — goes to Django, exactly as it would in
      // production where Django serves all of it.
      proxy: {
        [`^/(?!${appBase.slice(1, -1)}(/|$))`]: { target: backend, changeOrigin: false },
      },
    },
  }
})
