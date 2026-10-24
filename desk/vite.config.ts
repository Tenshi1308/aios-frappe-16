import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  server: {
    // Browser memetakan *.localhost ke ::1; karenanya halaman dev memakai
    // http://localhost:5173 dan proxy menyasar 127.0.0.1 (bench IPv4-only)
    // dengan Host header yang membuat Frappe meresolve site yang benar.
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: false,
        headers: { Host: 'aios-v16.localhost' },
      },
    },
  },
});
