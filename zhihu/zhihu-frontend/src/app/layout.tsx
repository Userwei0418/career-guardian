import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "职护 — 你的职场全方位保障",
  description: "AI 驱动的职场陪伴与决策辅助平台，陪你把碎片拼成一个能行动的决定。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col" suppressHydrationWarning>{children}</body>
    </html>
  );
}
