import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const adapter = env.VITE_DESKTOP_ADAPTER === 'mock' ? 'mock' : 'real';
  const modulesApiPath =
    adapter === 'mock'
      ? new URL('./src/api/mock/modules.ts', import.meta.url).pathname
      : new URL('./src/api/modules.ts', import.meta.url).pathname;

  const backendTarget = env.VITE_BACKEND_TARGET;
  const devPort = env.VITE_DEV_PORT;

  if (!backendTarget) {
    throw new Error('VITE_BACKEND_TARGET belum diisi. Salin .env.example ke .env lalu isi.');
  }
  if (!devPort) {
    throw new Error('VITE_DEV_PORT belum diisi. Salin .env.example ke .env lalu isi.');
  }

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@modules-api': modulesApiPath,
      },
    },
    server: {
      // Akses dev memakai <site>.localhost:<port> supaya Frappe memilih site
      // yang benar dari Host header (docs.frappe.io Sites § Site Resolution).
      // JANGAN menimpa Host di sini: override Host membuat semua request
      // dilayani sebagai satu site saja.
      // Backend IPv4 (bench hanya listen di 127.0.0.1); target dibaca dari env.
      host: true,
      port: Number(devPort),
      strictPort: true,
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: false,
        },
        // File privat artefak (/private/files/...) juga dilayani backend Frappe.
        '/private': {
          target: backendTarget,
          changeOrigin: false,
        },
      },
    },
  };
});
