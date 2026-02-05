import { defineConfig } from 'vite';
import path from 'path';
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
      tailwindcss()
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './assets/js'),
    },
  },
  base: '/static/', // Should match Django's STATIC_URL
  build: {
    manifest: true, // The manifest.json file is needed for django-vite
    outDir: path.resolve(__dirname, './static'), // Output directory for production build
    emptyOutDir: false, // Preserve the outDir to not clobber Django's other files.
    rollupOptions: {
      input: {
        'site-tailwind-css': path.resolve(__dirname, './assets/css/site.css'),
        site: path.resolve(__dirname, './assets/js/site.js'),
      },
      output: {
        // Output JS bundles to js/ directory with -bundle suffix
        entryFileNames: `js/[name]-bundle-[hash].js`,
        // For shared chunks, keep hash for cache busting
        chunkFileNames: `js/[name]-[hash].js`,
        // For CSS and other assets
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith('.css')) {
            // Try to name CSS files like css/[entry_name].css, removing potential hash
            let baseName = path.basename(assetInfo.name, '.css');
            const hashPattern = /\.[0-9a-fA-F]{8}$/;
            baseName = baseName.replace(hashPattern, '');
            return `css/${baseName}-[hash].css`;
          }
          // Default for other assets (fonts, images, etc.)
          return `assets/[name]-[hash][extname]`;
        },
      },
    },
  },
  server: {
    port: 5173, // Default Vite dev server port, must match DJANGO_VITE settings
    strictPort: true, // Vite will exit if the port is already in use
    hmr: {
      // host: 'localhost', // default of localhost is fine as long as Django is running there.
      // protocol: 'ws', // default of ws is fine. Change to 'wss' if Django (dev) server uses HTTPS.
    },
  },
});
