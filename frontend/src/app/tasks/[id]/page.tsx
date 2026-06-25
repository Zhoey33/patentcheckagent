"use client";

// 这个文件用于展示单个专利审查任务详情和 Markdown 报告。

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  CheckCircle2,
  Circle,
  Clipboard,
  Download,
  Loader2,
  RotateCcw,
  XCircle
} from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiFetch, ApiError } from "@/lib/api";
import type { PatentCheckReport, PatentCheckTask } from "@/lib/types";
import { useCurrentUser } from "@/hooks/useCurrentUser";

const stepStyleMap: Record<string, { dot: string; text: string; line: string }> = {
  done: {
    dot: "border-emerald-500 bg-emerald-500 text-white",
    text: "text-ink",
    line: "bg-emerald-500"
  },
  running: {
    dot: "border-accent bg-white text-accent",
    text: "text-accent",
    line: "bg-line"
  },
  failed: {
    dot: "border-red-500 bg-red-500 text-white",
    text: "text-danger",
    line: "bg-line"
  },
  pending: {
    dot: "border-line bg-white text-muted",
    text: "text-muted",
    line: "bg-line"
  }
};

function clampProgress(value: number | undefined) {
  return Math.max(0, Math.min(100, value ?? 0));
}

function ProgressIcon({ status }: { status: string }) {
  if (status === "done") return <CheckCircle2 className="h-4 w-4" />;
  if (status === "failed") return <XCircle className="h-4 w-4" />;
  if (status === "running") return <Loader2 className="h-4 w-4 animate-spin" />;
  return <Circle className="h-4 w-4" />;
}

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user, loading } = useCurrentUser();
  const [task, setTask] = useState<PatentCheckTask | null>(null);
  const [report, setReport] = useState<PatentCheckReport | null>(null);
  const [error, setError] = useState("");

  const shouldPoll = task?.status === "pending" || task?.status === "running";
  const progressPercent = clampProgress(task?.progress_percent ?? report?.progress_percent);
  const progressMessage = task?.progress_message ?? report?.progress_message ?? "等待任务状态更新。";
  const progressSteps = task?.progress_steps ?? report?.progress_steps ?? [];

  async function loadTask() {
    try {
      setError("");
      const [nextTask, nextReport] = await Promise.all([
        apiFetch<PatentCheckTask>(`/api/patent-checks/${id}`),
        apiFetch<PatentCheckReport>(`/api/patent-checks/${id}/report`)
      ]);
      setTask(nextTask);
      setReport(nextReport);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载任务失败。");
    }
  }

  useEffect(() => {
    if (!loading) {
      void loadTask();
    }
  }, [loading, id]);

  useEffect(() => {
    if (!shouldPoll) return;
    const timer = window.setInterval(() => {
      void loadTask();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [shouldPoll, id]);

  const markdown = useMemo(() => report?.final_report || "", [report]);

  async function copyReport() {
    if (markdown) {
      await navigator.clipboard.writeText(markdown);
    }
  }

  function downloadReport() {
    if (!markdown || !task) return;
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${task.title || "patent-check-report"}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function retryTask() {
    await apiFetch<PatentCheckTask>(`/api/patent-checks/${id}/retry`, { method: "POST" });
    await loadTask();
  }

  if (loading) {
    return <div className="p-6 text-sm text-muted">加载中...</div>;
  }

  return (
    <AppShell user={user}>
      <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <Link href="/tasks" className="text-sm text-accent hover:underline">返回历史记录</Link>
          <h1 className="mt-2 text-2xl font-semibold text-ink">{task?.title || "任务详情"}</h1>
          <p className="mt-1 text-sm text-muted">{task?.technical_field || "未填写技术领域"}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={copyReport}
            disabled={!markdown}
            className="inline-flex h-10 items-center gap-2 rounded border border-line bg-white px-3 text-sm text-ink hover:bg-panel disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Clipboard className="h-4 w-4" />
            复制
          </button>
          <button
            type="button"
            onClick={downloadReport}
            disabled={!markdown}
            className="inline-flex h-10 items-center gap-2 rounded border border-line bg-white px-3 text-sm text-ink hover:bg-panel disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            下载
          </button>
          {task?.status === "failed" ? (
            <button
              type="button"
              onClick={retryTask}
              className="inline-flex h-10 items-center gap-2 rounded bg-accent px-3 text-sm font-semibold text-white"
            >
              <RotateCcw className="h-4 w-4" />
              重试
            </button>
          ) : null}
        </div>
      </div>

      {error ? <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">{error}</div> : null}

      {task ? (
        <section className="mb-4 grid gap-4 rounded border border-line bg-white p-4 md:grid-cols-4">
          <div>
            <div className="text-xs text-muted">状态</div>
            <div className="mt-1"><StatusBadge status={task.status} /></div>
          </div>
          <div>
            <div className="text-xs text-muted">创建时间</div>
            <div className="mt-1 text-sm text-ink">{new Date(task.created_at).toLocaleString()}</div>
          </div>
          <div>
            <div className="text-xs text-muted">完成时间</div>
            <div className="mt-1 text-sm text-ink">{task.finished_at ? new Date(task.finished_at).toLocaleString() : "-"}</div>
          </div>
          <div>
            <div className="text-xs text-muted">文本字数</div>
            <div className="mt-1 text-sm text-ink">
              {task.claims_text_length + task.specification_text_length + task.drawings_text_length + task.abstract_text_length}
            </div>
          </div>
        </section>
      ) : null}

      {task ? (
        <section className="mb-4 rounded border border-line bg-white p-4">
          <div className="mb-3 flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
            <div>
              <h2 className="text-base font-semibold text-ink">审查进度</h2>
              <p className="mt-1 text-sm text-muted">{progressMessage}</p>
            </div>
            <div className="text-sm font-semibold text-accent">{progressPercent}%</div>
          </div>
          <div className="h-2 overflow-hidden rounded bg-panel">
            <div
              className="h-full rounded bg-accent transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          {progressSteps.length ? (
            <div className="mt-4 grid gap-3 md:grid-cols-6">
              {progressSteps.map((step, index) => {
                const style = stepStyleMap[step.status] || stepStyleMap.pending;
                return (
                  <div key={step.key} className="relative flex gap-2 md:block">
                    {index < progressSteps.length - 1 ? (
                      <div
                        className={[
                          "absolute left-4 top-8 h-[calc(100%-1rem)] w-px",
                          "md:left-[calc(50%+1rem)] md:top-4 md:h-px md:w-[calc(100%-2rem)]",
                          style.line
                        ].join(" ")}
                      />
                    ) : null}
                    <div className="relative z-10 flex md:justify-center">
                      <span
                        className={`inline-flex h-8 w-8 items-center justify-center rounded-full border ${style.dot}`}
                      >
                        <ProgressIcon status={step.status} />
                      </span>
                    </div>
                    <div className={`min-w-0 pt-1 text-sm md:mt-2 md:text-center ${style.text}`}>
                      {step.label}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : null}
        </section>
      ) : null}

      {task?.files.length ? (
        <section className="mb-4 rounded border border-line bg-white p-4">
          <h2 className="mb-3 text-base font-semibold text-ink">上传文件</h2>
          <div className="grid gap-2 md:grid-cols-2">
            {task.files.map((file) => (
              <div key={file.id} className="rounded border border-line p-3 text-sm">
                <div className="font-medium text-ink">{file.original_filename}</div>
                <div className="mt-1 text-muted">
                  {file.file_role} · {Math.round(file.file_size_bytes / 1024)} KB · 抽取 {file.extracted_text_length} 字
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {task?.error_message ? (
        <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">{task.error_message}</div>
      ) : null}

      <section className="rounded border border-line bg-white p-5">
        {markdown ? (
          <div className="markdown-body max-h-[72vh] overflow-auto">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
          </div>
        ) : (
          <div className="py-16 text-center text-sm text-muted">
            {shouldPoll ? progressMessage : "暂无报告。"}
          </div>
        )}
      </section>
    </AppShell>
  );
}
