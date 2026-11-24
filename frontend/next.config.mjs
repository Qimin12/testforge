/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 后端在 localhost:8000，前端 3000；浏览器直连后端（CORS 已在后端配置）
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
