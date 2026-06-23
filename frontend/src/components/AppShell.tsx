"use client";

// 这个文件用于提供业务页面的顶部导航和整体布局。

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, ScrollText, UploadCloud } from "lucide-react";

import { logout } from "@/lib/api";
import type { User } from "@/lib/types";

type AppShellProps = {
  user: User | null;
  children: React.ReactNode;
};

export function AppShell({ user, children }: AppShellProps) {
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <div className="min-h-screen bg-panel">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link href="/workspace" className="flex min-w-0 items-center gap-3">
            <Image
              src="/lab-logo.jpg"
              alt="实验室 Logo"
              width={40}
              height={40}
              className="h-10 w-10 rounded object-cover"
            />
            <div className="min-w-0">
              <div className="truncate text-base font-semibold text-ink">专利文件智能审查系统</div>
              <div className="text-xs text-muted">实验室内部审查工作台</div>
            </div>
          </Link>
          <nav className="flex items-center gap-2">
            <Link
              href="/workspace"
              className="inline-flex h-9 items-center gap-2 rounded border border-line bg-white px-3 text-sm text-ink hover:bg-panel"
            >
              <UploadCloud className="h-4 w-4" />
              审查
            </Link>
            <Link
              href="/tasks"
              className="inline-flex h-9 items-center gap-2 rounded border border-line bg-white px-3 text-sm text-ink hover:bg-panel"
            >
              <ScrollText className="h-4 w-4" />
              历史
            </Link>
            <div className="hidden text-sm text-muted sm:block">{user?.username}</div>
            <button
              type="button"
              onClick={handleLogout}
              className="inline-flex h-9 w-9 items-center justify-center rounded border border-line bg-white text-ink hover:bg-panel"
              title="退出登录"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
