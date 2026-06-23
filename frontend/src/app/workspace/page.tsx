"use client";

// 这个文件用于提供专利审查任务上传工作台。

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, Send } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { apiFetch, ApiError } from "@/lib/api";
import type { PatentCheckTask } from "@/lib/types";
import { useCurrentUser } from "@/hooks/useCurrentUser";

const fileFields = [
  { name: "claims", label: "权利要求书文件", required: true },
  { name: "specification", label: "说明书文件", required: true },
  { name: "drawings", label: "附图说明文件", required: true },
  { name: "abstract", label: "摘要文件", required: false }
] as const;

export default function WorkspacePage() {
  const router = useRouter();
  const { user, loading } = useCurrentUser();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    const form = new FormData(event.currentTarget);
    try {
      const task = await apiFetch<PatentCheckTask>("/api/patent-checks", {
        method: "POST",
        body: form
      });
      router.push(`/tasks/${task.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "提交失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <div className="p-6 text-sm text-muted">加载中...</div>;
  }

  return (
    <AppShell user={user}>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold text-ink">审查工作台</h1>
        <p className="mt-1 text-sm text-muted">上传可复制文本型 PDF，任务会异步执行，提交后可在详情页查看进度。</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5 rounded border border-line bg-white p-5">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">任务标题</span>
            <input
              name="title"
              className="h-10 w-full rounded border border-line px-3 outline-none focus:border-accent"
              placeholder="例如：一种数据处理方法审查"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">技术领域</span>
            <input
              name="technical_field"
              className="h-10 w-full rounded border border-line px-3 outline-none focus:border-accent"
              placeholder="人工智能、通信、机械、材料、化学等"
            />
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {fileFields.map((field) => (
            <label key={field.name} className="block rounded border border-line p-4">
              <span className="mb-2 flex items-center gap-2 text-sm font-medium text-ink">
                <FileText className="h-4 w-4 text-accent" />
                {field.label}
                {field.required ? <span className="text-danger">*</span> : null}
              </span>
              <input
                name={field.name}
                type="file"
                accept="application/pdf,.pdf"
                required={field.required}
                className="block w-full text-sm text-muted file:mr-3 file:h-9 file:rounded file:border-0 file:bg-panel file:px-3 file:text-sm file:text-ink"
              />
            </label>
          ))}
        </div>

        <div className="rounded border border-line bg-panel px-3 py-2 text-sm text-muted">
          单个文件不超过 20 MB，单个任务最多 4 个 PDF，总抽取文本不超过 200,000 个中文字符。扫描件 PDF 暂不支持 OCR。
        </div>

        {error ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">{error}</div> : null}

        <button
          type="submit"
          disabled={submitting}
          className="inline-flex h-10 items-center gap-2 rounded bg-accent px-4 text-sm font-semibold text-white hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Send className="h-4 w-4" />
          {submitting ? "提交中" : "开始审查"}
        </button>
      </form>
    </AppShell>
  );
}
