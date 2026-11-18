import { fileURLToPath, URL } from 'node:url';

import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import Components from 'unplugin-vue-components/vite';
import { BootstrapVueNextResolver } from 'bootstrap-vue-next';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const envDir = fileURLToPath(new URL('.', import.meta.url));
  const env = loadEnv(mode, envDir, 'VITE_');
  const frappeUrl = env.VITE_FRAPPE_URL;

  if (!frappeUrl) {
    throw new Error('VITE_FRAPPE_URL belum diatur di frontend/.env');
  }

  return {
    base: "/",
    server: {
      proxy: {
        "/api": {
          target: frappeUrl,
          changeOrigin: true,
          headers: {
            "X-Frappe-Site-Name": "fintoedu.local",
          },
        },
        "/files": {
          target: frappeUrl,
          changeOrigin: true,
          headers: {
            "X-Frappe-Site-Name": "fintoedu.local",
          },
        },
        // File privat (mis. wallpaper desktop pribadi): hanya bisa dibuka pemiliknya.
        "/private": {
          target: frappeUrl,
          changeOrigin: true,
          headers: {
            "X-Frappe-Site-Name": "fintoedu.local",
          },
        },
      },
    },
    plugins: [
      vue(),
      Components({
        resolvers: [BootstrapVueNextResolver()],
      }),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    }
  };
});
