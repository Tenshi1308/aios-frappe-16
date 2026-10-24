# Ekasa Desk (`desk/`)

Frontend Vue 3 + Vite + TypeScript + Pinia + Vue Router untuk desktop AIOS.
Struktur mengikuti `docs/08` §9; token visual di `src/styles/tokens.css`.

## Perintah

```bash
npm install
npm run dev         # http://localhost:5173 (strictPort)
npm run typecheck   # vue-tsc --noEmit
npm run build       # typecheck + vite build
```

Dev server mem-proxies `/api` ke bench lokal (`http://127.0.0.1:8001`,
`Host: aios-v16.localhost`) sehingga browser cukup membuka
`http://localhost:5173` — Chrome memetakan `*.localhost` ke `::1` sementara
bench hanya bind IPv4, jadi jangan membuka via `aios-v16.localhost:5173`.

## Aturan penting

- Font Plus Jakarta Sans + JetBrains Mono dibundel lokal di
  `src/assets/fonts/` (lisensi OFL 1.1, lihat `OFL.txt`) — tanpa CDN.
- Warna/radius/shadow hanya lewat token di `styles/tokens.css`; tidak ada
  hex/rgba di `components/` dan `views/`.
- Tanpa `v-html`, tanpa `localStorage` untuk token/CSRF.
- Nama agent, saran, dan data lain selalu dari backend (`/api/branches`,
  `get_session_context`) — tidak ada hardcode.
