// 这个文件用于定义 Next.js 应用的根布局和全局元数据。

import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "专利文件智能审查系统",
  description: "实验室内部专利文件智能审查系统"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
