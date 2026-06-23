// 这个文件用于将应用根路径导向登录页。

import { redirect } from "next/navigation";

export default function HomePage() {
  redirect("/login");
}
