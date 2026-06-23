"use client";

// 这个文件用于提供专利审查历史任务列表。

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Search } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiFetch, ApiError } from "@/lib/api";
import type { PatentCheckTaskList } from "@/lib/types";
import { useCurrentUser } from "@/hooks/useCurrentUser";

export default function TasksPage() {
  const { user, loading } = useCurrentUser();
  const [data, setData] = useState<PatentCheckTaskList | null>(null);
  const [status, setStatus] = useState("");
  const [keyword, setKeyword] = useState("");
  const [error, setError] = useState("");

  async function loadTasks(nextStatus = status, nextKeyword = keyword) {
    const params = new URLSearchParams();
    if (nextStatus) params.set("status", nextStatus);
    if (nextKeyword) params.set("keyword", nextKeyword);
    try {
      setError("");
      setData(await apiFetch<PatentCheckTaskList>(`/api/patent-checks?${params.toString()}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载任务失败。");
    }
  }

  useEffect(() => {
    if (!loading) {
      void loadTasks();
    }
  }, [loading]);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadTasks(status, keyword);
  }

  if (loading) {
    return <div className="p-6 text-sm text-muted">加载中...</div>;
  }

  return (
    <AppShell user={user}>
      <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <h1 className="text-2xl font-semibold text-ink">历史记录</h1>
          <p className="mt-1 text-sm text-muted">查看已提交任务、状态和报告。</p>
        </div>
        <Link href="/workspace" className="inline-flex h-10 items-center justify-center rounded bg-accent px-4 text-sm font-semibold text-white">
          新建审查
        </Link>
      </div>

      <form onSubmit={handleSearch} className="mb-4 flex flex-col gap-3 rounded border border-line bg-white p-4 sm:flex-row">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="h-10 rounded border border-line px-3 text-sm outline-none focus:border-accent"
        >
          <option value="">全部状态</option>
          <option value="pending">等待执行</option>
          <option value="running">审查中</option>
          <option value="succeeded">已完成</option>
          <option value="failed">失败</option>
        </select>
        <input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          className="h-10 min-w-0 flex-1 rounded border border-line px-3 text-sm outline-none focus:border-accent"
          placeholder="按任务标题搜索"
        />
        <button type="submit" className="inline-flex h-10 items-center justify-center gap-2 rounded border border-line bg-white px-4 text-sm text-ink hover:bg-panel">
          <Search className="h-4 w-4" />
          搜索
        </button>
      </form>

      {error ? <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">{error}</div> : null}

      <div className="overflow-hidden rounded border border-line bg-white">
        <div className="grid grid-cols-[1fr_96px_160px] border-b border-line bg-panel px-4 py-3 text-sm font-medium text-muted md:grid-cols-[1fr_110px_180px_160px]">
          <div>任务</div>
          <div>状态</div>
          <div className="hidden md:block">完成时间</div>
          <div>创建时间</div>
        </div>
        {data?.items.length ? (
          data.items.map((task) => (
            <Link
              key={task.id}
              href={`/tasks/${task.id}`}
              className="grid grid-cols-[1fr_96px_160px] items-center border-b border-line px-4 py-3 text-sm last:border-b-0 hover:bg-panel md:grid-cols-[1fr_110px_180px_160px]"
            >
              <div className="min-w-0">
                <div className="truncate font-medium text-ink">{task.title}</div>
                <div className="truncate text-xs text-muted">{task.technical_field || "未填写技术领域"}</div>
              </div>
              <div><StatusBadge status={task.status} /></div>
              <div className="hidden text-muted md:block">{task.finished_at ? new Date(task.finished_at).toLocaleString() : "-"}</div>
              <div className="text-muted">{new Date(task.created_at).toLocaleString()}</div>
            </Link>
          ))
        ) : (
          <div className="px-4 py-10 text-center text-sm text-muted">暂无审查任务</div>
        )}
      </div>
    </AppShell>
  );
}
