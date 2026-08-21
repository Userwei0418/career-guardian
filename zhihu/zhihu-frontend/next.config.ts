import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* API 同源代理由 src/app/api/[...path]/route.ts 处理。 */
  // 独立验收服务可使用单独构建目录，避免占用正在运行的 .next/dev 锁。
  distDir: process.env.NEXT_DIST_DIR || ".next",
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
