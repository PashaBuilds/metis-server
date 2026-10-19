import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Derleme göreli yollarla: sunucu index.html'e <base href> yazar; aynı paket kökte ya da bir alt yolda (/metis) çalışır.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? './' : '/',
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  build: {
    target: 'es2022',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('@xyflow') || id.includes('elkjs')) return 'graph';
          if (id.includes('react-markdown') || id.includes('remark') || id.includes('rehype') || id.includes('micromark') || id.includes('mdast') || id.includes('hast')) return 'markdown';
          if (id.includes('prism-react-renderer')) return 'prism';
          return undefined;
        },
      },
    },
  },
}));
