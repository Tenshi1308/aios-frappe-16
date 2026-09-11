import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  assetPrefix: "/assets/aios_v1/frontend",
  images: {
    unoptimized: true,
  },
};

export default nextConfig;

