"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AppShell } from "@/components/AppShell";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { apiFetch } from "@/lib/api";
import type { ReviewSkill, ReviewSkillDetail } from "@/lib/types";

const initialFiles = { "SKILL.md": `---
name: patent-review-custom
description: 根据已有专利材料执行两阶段质量检查，输出有原文依据的中文报告。
---

# 专利材料检查

直接读取任务给出的原文件。按照任务指定阶段审查，输出对应阶段的 Markdown 报告。
每个问题注明原文位置、实际影响和最小修改方向。不能辨读或未读完的内容须说明。

请在这里补充具体审查规则，或导入现有 SKILL.md。
` };
const button = "rounded border border-line bg-white px-3 py-2 text-sm hover:bg-panel disabled:opacity-50";
const input = "w-full rounded border border-line px-3 py-2 text-sm";

export default function SkillsPage() {
  const { user, loading } = useCurrentUser();
  const [items, setItems] = useState<ReviewSkill[]>([]);
  const [selected, setSelected] = useState<ReviewSkillDetail | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [files, setFiles] = useState<Record<string, string>>({});
  const [file, setFile] = useState("SKILL.md");
  const [reference, setReference] = useState("");
  const [preview, setPreview] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function refresh() {
    const data = await apiFetch<{ items: ReviewSkill[] }>("/api/admin/skills");
    setItems(data.items);
  }
  useEffect(() => {
    if (user?.role === "admin") refresh().catch(() => setError("加载失败，请刷新页面重试。"));
  }, [user]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function loadEditor(skill: ReviewSkillDetail | null) {
    setSelected(skill); setName(skill?.display_name || "自定义专利检查");
    setEnabled(skill?.is_enabled ?? true); setFiles(skill?.files || { ...initialFiles });
    setFile("SKILL.md"); setPreview(false); setEditing(true); setDirty(false); setReference("");
  }
  function canSwitch() { return !dirty || window.confirm("有尚未保存的修改，确定放弃吗？"); }
  async function open(skill: ReviewSkill) {
    if (!canSwitch()) return;
    setBusy(true); setError(""); setMessage("");
    try { loadEditor(await apiFetch<ReviewSkillDetail>(`/api/admin/skills/${skill.id}`)); }
    catch (err) { setError(err instanceof Error ? err.message : "打开失败。"); }
    finally { setBusy(false); }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const result = await apiFetch<ReviewSkillDetail>(selected ? `/api/admin/skills/${selected.id}` : "/api/admin/skills", {
        method: selected ? "PUT" : "POST",
        body: JSON.stringify({ display_name: name, is_enabled: enabled, files, ...(selected ? { version: selected.version } : {}) })
      });
      loadEditor(result); await refresh(); setMessage(`已保存 v${result.version}。新任务将使用此版本，已有任务不受影响。`);
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败。"); }
    finally { setBusy(false); }
  }
  async function action(kind: "default" | "delete") {
    if (!selected || dirty) return;
    if (kind === "delete" && !window.confirm(`删除“${selected.display_name}”？历史任务仍保留所用规则。`)) return;
    setBusy(true); setError(""); setMessage("");
    try {
      if (kind === "delete") {
        await apiFetch<void>(`/api/admin/skills/${selected.id}`, { method: "DELETE" });
        setEditing(false); setSelected(null); setMessage("已删除 Skill。");
      } else {
        loadEditor(await apiFetch<ReviewSkillDetail>(`/api/admin/skills/${selected.id}/default`, { method: "POST" }));
        setMessage("已设为默认审查 Skill。");
      }
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "操作失败。"); }
    finally { setBusy(false); }
  }
  function addReference() {
    const value = reference.trim();
    const path = value.startsWith("references/") ? value : `references/${value}`;
    if (!/^references\/[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*\.md$/.test(path)) {
      setError("请使用英文文件名，例如 claims.md 或 references/claims.md。"); return;
    }
    if (files[path] !== undefined) { setError("这个文件已存在。"); return; }
    setFiles({ ...files, [path]: "# 参考规则\n\n" }); setFile(path); setReference(""); setDirty(true); setError("");
  }
  async function importFiles(event: React.ChangeEvent<HTMLInputElement>) {
    const uploads = Array.from(event.target.files || []);
    event.target.value = "";
    if (!uploads.length) return;
    if (uploads.some((item) => !item.name.endsWith(".md")) || uploads.reduce((sum, item) => sum + item.size, 0) > 512000) {
      setError("请选择 Markdown 文件，总大小不超过 500 KB。"); return;
    }
    const incoming: Record<string, string> = {};
    for (const item of uploads) incoming[item.name === "SKILL.md" ? "SKILL.md" : `references/${item.name}`] = await item.text();
    if (Object.keys(incoming).some((path) => files[path] !== undefined) && !window.confirm("导入将覆盖编辑器中同名文件，是否继续？")) return;
    setFiles({ ...files, ...incoming }); setDirty(true); setError("");
  }

  if (loading) return <div className="p-6 text-sm text-muted">加载中...</div>;
  if (user?.role !== "admin") return <AppShell user={user}><p>仅管理员可以管理审查 Skill。</p></AppShell>;
  return (
    <AppShell user={user}>
      <div className="mb-5 flex items-start justify-between gap-4">
        <div><h1 className="text-2xl font-semibold">审查 Skills</h1><p className="mt-1 text-sm text-muted">维护审查规则、参考文件与默认设置。保存后应用于新任务。</p></div>
        <button className={button} disabled={busy} onClick={() => { if (canSwitch()) { loadEditor(null); setError(""); setMessage(""); } }}>新建 Skill</button>
      </div>
      {error && <p role="alert" className="mb-4 rounded bg-red-50 p-3 text-sm text-danger">{error}</p>}
      {message && <p role="status" className="mb-4 rounded bg-green-50 p-3 text-sm text-green-800">{message}</p>}
      <div className="grid items-start gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="space-y-2">
          {items.map((skill) => <button key={skill.id} disabled={busy} onClick={() => open(skill)} className={`w-full rounded border bg-white p-4 text-left ${selected?.id === skill.id ? "border-accent" : "border-line"}`}>
            <div className="font-medium">{skill.display_name}</div>
            <div className="mt-1 text-xs text-muted">{skill.name} · v{skill.version}</div>
            <div className="mt-2 text-xs text-accent">{skill.is_default ? "默认 · " : ""}{skill.is_enabled ? "已启用" : "已停用"}</div>
          </button>)}
        </aside>
        {editing ? <form onSubmit={save} className="min-w-0 space-y-4 rounded border border-line bg-white p-5">
          <fieldset disabled={busy} className="min-w-0 space-y-4 disabled:opacity-70">
            <div className="flex flex-wrap items-end gap-4">
              <label className="min-w-48 flex-1 text-sm">显示名称<input className={`${input} mt-1`} required maxLength={128} value={name} onChange={(e) => { setName(e.target.value); setDirty(true); }} /></label>
              <label className="py-2 text-sm"><input type="checkbox" checked={enabled} disabled={selected?.is_default} onChange={(e) => { setEnabled(e.target.checked); setDirty(true); }} className="mr-2" />启用</label>
            </div>
            <p className="text-xs text-muted">SKILL.md 定义名称、用途和审查流程。references/ 保存补充规则，在正文中用相对链接引用。仅支持 Markdown 规则文件。</p>
            <div className="flex flex-wrap items-center gap-2">
              <label className={`${button} cursor-pointer`}>导入 .md 文件<input type="file" accept=".md,text/markdown" multiple disabled={busy} className="sr-only" onChange={(event) => { importFiles(event).catch(() => setError("文件读取失败，请重试。")); }} /></label>
              <input aria-label="新增参考文件名" className={`${input} min-w-36 flex-1`} placeholder="参考文件名，例如 claims.md" value={reference} onChange={(e) => setReference(e.target.value)} />
              <button type="button" className={button} onClick={addReference} disabled={!reference.trim()}>添加参考文件</button>
            </div>
            <div className="flex flex-wrap gap-2" aria-label="Skill 文件">
              {Object.keys(files).map((path) => <button type="button" key={path} onClick={() => setFile(path)} className={`${button} ${file === path ? "border-accent text-accent" : ""}`}>{path}</button>)}
            </div>
            <div className="flex items-center justify-between text-sm">
              <span>{file}{dirty ? " · 未保存" : ""}</span>
              <div className="flex gap-2">
                {file !== "SKILL.md" && <button type="button" className={button} onClick={() => { if (window.confirm(`移除 ${file}？请同时更新正文中的引用。`)) { const next = { ...files }; delete next[file]; setFiles(next); setFile("SKILL.md"); setDirty(true); } }}>移除文件</button>}
                <button type="button" className={button} onClick={() => setPreview(!preview)}>{preview ? "编辑" : "预览"}</button>
              </div>
            </div>
            {preview ? <div className="prose max-w-none overflow-x-auto rounded border border-line p-4"><ReactMarkdown remarkPlugins={[remarkGfm]}>{files[file] || ""}</ReactMarkdown></div> : <textarea aria-label={file} spellCheck={false} rows={22} className={`${input} font-mono leading-6`} value={files[file] || ""} onChange={(e) => { setFiles({ ...files, [file]: e.target.value }); setDirty(true); }} />}
            <div className="flex flex-wrap gap-2">
              <button type="submit" className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={!!selected && !dirty}>{busy ? "处理中…" : "保存 Skill"}</button>
              {selected && !selected.is_default && <>
                <button type="button" className={button} disabled={dirty || !selected.is_enabled} onClick={() => action("default")}>设为默认</button>
                <button type="button" className={`${button} text-danger`} disabled={dirty} onClick={() => action("delete")}>删除</button>
              </>}
            </div>
          </fieldset>
        </form> : <div className="rounded border border-line bg-white p-10 text-center text-sm text-muted">选择一个 Skill 查看规则，或新建 Skill。</div>}
      </div>
    </AppShell>
  );
}
