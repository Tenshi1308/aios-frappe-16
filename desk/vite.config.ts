import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const adapter = env.VITE_DESKTOP_ADAPTER === 'mock' ? 'mock' : 'real';
  const modulesApiPath =
    adapter === 'mock'
      ? new URL('./src/api/mock/modules.ts', import.meta.url).pathname
      : new URL('./src/api/modules.ts', import.meta.url).pathname;

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@modules-api': modulesApiPath,
      },
    },
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
        // File privat artefak (/private/files/...) juga dilayani backend Frappe.
        '/private': {
          target: 'http://127.0.0.1:8001',
          changeOrigin: false,
          headers: { Host: 'aios-v16.localhost' },
        },
      },
    },
  };
});
