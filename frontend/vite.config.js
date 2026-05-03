import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

const analyze = process.env.ANALYZE === 'true';

// Pre-compresses static assets at build time. The FastAPI app serves
// uncompressed bundles and lets ``GZipMiddleware`` gzip on the fly,
// so the ``.gz`` / ``.br`` siblings only add value when a reverse
// proxy (nginx with ``gzip_static``/``brotli_static``, Caddy, or a
// CDN) is in front and can serve them directly without recompressing.
// ``vite-plugin-compression2`` is a soft dep: when it isn't installed
// the build still succeeds, it just skips emitting the siblings.
async function maybeCompression() {
  try {
    const mod = await import('vite-plugin-compression2');
    const compression = mod.compression || mod.default;
    return [
      compression({ algorithm: 'gzip', threshold: 1024 }),
      compression({ algorithm: 'brotliCompress', threshold: 1024 }),
    ];
  } catch {
    return [];
  }
}

async function maybeVisualizer() {
  if (!analyze) return null;
  try {
    const { visualizer } = await import('rollup-plugin-visualizer');
    return visualizer({
      filename: 'dist/stats.html',
      template: 'treemap',
      gzipSize: true,
      brotliSize: true,
      open: false,
    });
  } catch {
    console.warn(
      'ANALYZE=true requires rollup-plugin-visualizer. Install with: ' +
      'npm i -D rollup-plugin-visualizer',
    );
    return null;
  }
}

export default defineConfig(async () => ({
  plugins: [
    react(),
    await maybeVisualizer(),
    ...(await maybeCompression()),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['fonts/**/*', 'icon.svg'],
      manifest: {
        name: 'Volley Scoreboard',
        short_name: 'Volley',
        description: 'Touch-friendly volleyball scoreboard controller',
        theme_color: '#1a1a2e',
        background_color: '#1a1a2e',
        display: 'standalone',
        orientation: 'any',
        start_url: '/',
        icons: [
          {
            src: 'icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any',
          },
          {
            src: 'icon-192x192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any maskable',
          },
          {
            src: 'icon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,ttf,otf}'],
        navigateFallback: 'index.html',
        navigateFallbackDenylist: [
          /^\/api/, /^\/fonts/, /^\/pwa/, /^\/health/,
          /^\/overlay/, /^\/ws(\/|\?|$)/, /^\/static/,
          /^\/(create|delete|list|manage)(\/|\?|$)/,
          // Server-rendered match-history surfaces. Without these the SW
          // would serve the SPA shell and the operator would land back on
          // the scoreboard instead of the report / index page.
          /^\/match(es)?(\/|\?|$)/,
        ],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-stylesheets',
              expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
            },
          },
          {
            urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-webfonts',
              expiration: { maxEntries: 30, maxAgeSeconds: 60 * 60 * 24 * 365 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      // Exclude generated types, the test harness itself, and entry shims
      // that are exercised by integration paths but not by unit tests.
      exclude: [
        'src/api/schema.d.ts',
        'src/test/**',
        'src/main.tsx',
        'src/PreviewApp.tsx',
      ],
      // Thresholds act as a regression floor — pinned tightly below
      // current coverage at the time of introduction so a drop fails CI
      // and a recovery pass can ratchet them upward. Bump these whenever
      // you raise coverage; do not lower them to make CI green.
      thresholds: {
        lines: 72,
        statements: 70,
        functions: 57,
        branches: 60,
      },
    },
  },
}));
