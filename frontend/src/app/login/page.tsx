"use client";

// 这个文件用于提供内部用户登录页面。

import Image from "next/image";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";

import { apiFetch, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await apiFetch<User>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password })
      });
      router.push("/workspace");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-panel px-4 py-10">
      <section className="w-full max-w-md rounded border border-line bg-white p-8 shadow-sm">
        <div className="mb-8 flex items-center gap-4">
          <Image
            src="/lab-logo.jpg"
            alt="实验室 Logo"
            width={64}
            height={64}
            className="h-16 w-16 rounded object-cover"
            priority
          />
          <div>
            <h1 className="text-xl font-semibold text-ink">专利文件智能审查系统</h1>
            <p className="mt-1 text-sm text-muted">实验室内部账号登录</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">账号</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="h-11 w-full rounded border border-line px-3 outline-none focus:border-accent"
              autoComplete="username"
              required
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">密码</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="h-11 w-full rounded border border-line px-3 outline-none focus:border-accent"
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
          {error ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">{error}</div> : null}
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded bg-accent px-4 text-sm font-semibold text-white hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <LogIn className="h-4 w-4" />
            {submitting ? "登录中" : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
