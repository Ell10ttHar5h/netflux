import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow hot-reload (HMR) connections from other LAN machines during `next dev`
  allowedDevOrigins: ["192.168.1.183", "100.125.207.32"],
};

export default nextConfig;
