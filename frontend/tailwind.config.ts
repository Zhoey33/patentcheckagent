// 这个文件用于声明 Tailwind CSS 扫描路径和主题扩展。

import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17212b",
        muted: "#5f6f7a",
        line: "#d8e1e7",
        panel: "#f6f8fa",
        accent: "#1d6f87",
        warn: "#a05a00",
        danger: "#b42318"
      }
    }
  },
  plugins: []
};

export default config;
