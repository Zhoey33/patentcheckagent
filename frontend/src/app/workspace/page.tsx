"use client";

// 这个文件用于提供专利审查任务上传工作台。

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, Send } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { apiFetch, ApiError } from "@/lib/api";
import type { PatentCheckTask, ReviewSkill } from "@/lib/types";
import { useCurrentUser } from "@/hooks/useCurrentUser";

const fileFields = [
  { name: "claims", label: "权利要求书文件", required: true },
  { name: "specification", label: "说明书文件", required: true },
  { name: "drawings", label: "附图说明文件", required: false },
  { name: "abstract", label: "摘要文件", required: false }
] as const;

export default function WorkspacePage() {
  const router = useRouter();
  const { user, loading } = useCurrentUser();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [skills, setSkills] = useState<ReviewSkill[]>([]);
  const [skillId, setSkillId] = useState("");
  useEffect(() => {
    if (!user) return;
    apiFetch<{ items: ReviewSkill[] }>("/api/skills").then(({ items }) => {
      setSkills(items);
      setSkillId((items.find((skill) => skill.is_default) || items[0])?.id || "");
    }).catch(() => setError("审查规则加载失败，请刷新页面重试。"));
  }, [user]);

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
        <p className="mt-1 text-sm text-muted">上传 PDF 或 Word（.docx）原文件，Codex 将按所选 Skill 阅读材料并生成报告。</p>
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

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">审查 Skill</span>
          <select name="skill_id" value={skillId} onChange={(e) => setSkillId(e.target.value)} required disabled={!skills.length} className="h-10 w-full rounded border border-line bg-white px-3">
            {!skills.length ? <option value="">暂无可用规则或正在加载</option> : null}
            {skills.map((skill) => <option key={skill.id} value={skill.id}>{skill.display_name} · v{skill.version}{skill.is_default ? "（默认）" : ""}</option>)}
          </select>
          <span className="mt-2 block text-sm text-muted">{skills.find((skill) => skill.id === skillId)?.description}</span>
        </label>

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
                accept="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.pdf,.docx"
                required={field.required}
                className="block w-full text-sm text-muted file:mr-3 file:h-9 file:rounded file:border-0 file:bg-panel file:px-3 file:text-sm file:text-ink"
              />
            </label>
          ))}
        </div>

        <div className="rounded border border-line bg-panel px-3 py-2 text-sm text-muted">
          单个文件不超过 20 MB，最多 4 个。扫描件 PDF 可上传，由 Codex 查看页面；模糊或无法辨读的内容会在报告中标明。任务失败时保留原文件供重试，完成或取消后清理。
        </div>

        {error ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">{error}</div> : null}

        <button
          type="submit"
          disabled={submitting || !skillId}
          className="inline-flex h-10 items-center gap-2 rounded bg-accent px-4 text-sm font-semibold text-white hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Send className="h-4 w-4" />
          {submitting ? "提交中" : "开始审查"}
        </button>
      </form>
    </AppShell>
  );
}
