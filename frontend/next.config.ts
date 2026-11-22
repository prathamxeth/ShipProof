import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";
    const storeUrl = process.env.INTERNAL_STORE_URL || "http://127.0.0.1:3005";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/store",
        destination: `${storeUrl}/`,
      },
      {
        source: "/store/:path*",
        destination: `${storeUrl}/:path*`,
      },
      {
        source: "/cart/:path*",
        destination: `${storeUrl}/cart/:path*`,
      },
      {
        source: "/cart",
        destination: `${storeUrl}/cart`,
      },
      {
        source: "/checkout/:path*",
        destination: `${storeUrl}/checkout/:path*`,
      },
      {
        source: "/checkout",
        destination: `${storeUrl}/checkout`,
      },
      {
        source: "/order-confirmation",
        destination: `${storeUrl}/order-confirmation`,
      },
      {
        source: "/product/:path*",
        destination: `${storeUrl}/product/:path*`,
      },
      {
        source: "/static/:path*",
        destination: `${storeUrl}/static/:path*`,
      },
    ];
  },
};

export default nextConfig;
