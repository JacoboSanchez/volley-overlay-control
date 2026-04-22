import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

const analyze = process.env.ANALYZE === 'true';

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
          /^\/overlay/, /^\/ws\//, /^\/static/,
          /^\/create\//, /^\/delete\//, /^\/list\//,
          /^\/manage(\/|\?|$)/,
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
  },
}));
