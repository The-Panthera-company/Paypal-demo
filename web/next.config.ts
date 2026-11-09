import type { NextConfig } from "next";

// Basic security headers for every page. No Content-Security-Policy yet: the PayPal SDK loads
// scripts and frames from several PayPal hosts, so a CSP needs testing against a live checkout.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Microphone only for this site (the Giving Agent's Speak button); no camera or location
  { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=(self), payment=(self)" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
