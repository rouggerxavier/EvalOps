/** @type {import('next').NextConfig} */
const nextConfig = {
  async headers() {
    return ["/forgot-password", "/reset-password"].map((source) => ({ source, headers: [
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "X-Robots-Tag", value: "noindex, nofollow" },
      { key: "Cache-Control", value: "no-store" },
    ] }));
  },
};

export default nextConfig;

