import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// Artefak build dilayani Frappe dari aios_v1/public/admin lewat /assets.
// base harus sama dengan prefix path aset di halaman www (aios_admin.py).
export default defineConfig({
  plugins: [vue()],
  base: '/assets/aios_v1/admin/',
  build: {
    outDir: '../aios_v1/public/admin',
    emptyOutDir: true,
    manifest: 'manifest.json',
  },
});
