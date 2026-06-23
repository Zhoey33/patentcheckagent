// 这个文件用于把审查任务状态渲染成统一的视觉标签。

const statusMap: Record<string, { label: string; className: string }> = {
  pending: { label: "等待执行", className: "bg-slate-100 text-slate-700" },
  running: { label: "审查中", className: "bg-cyan-100 text-cyan-800" },
  succeeded: { label: "已完成", className: "bg-emerald-100 text-emerald-800" },
  failed: { label: "失败", className: "bg-red-100 text-red-800" },
  cancelled: { label: "已取消", className: "bg-zinc-100 text-zinc-700" }
};

export function StatusBadge({ status }: { status: string }) {
  const item = statusMap[status] || { label: status, className: "bg-slate-100 text-slate-700" };

  return (
    <span className={`inline-flex rounded px-2 py-1 text-xs font-medium ${item.className}`}>
      {item.label}
    </span>
  );
}
