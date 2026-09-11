import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Baris "output: export" dan "assetPrefix" DIHAPUS (Penting! Biar CSS/JS-nya nggak hancur)
  images: {
    unoptimized: true,
  },
  // Tambahin proxy biar nembak Frappe
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:8083/api/:path*',
      },
    ];
  },
};

export default nextConfig;