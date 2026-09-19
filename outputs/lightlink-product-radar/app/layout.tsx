import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LightLink 外贸情报站",
  description: "面向单人外贸运营的跨平台关键词与产品机会工作台。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">{children}</body>
    </html>
  );
}
