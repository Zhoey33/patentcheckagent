// 这个文件用于把专利审查执行事件转换为用户可读的前端展示文案。

import type { PatentCheckEvent } from "@/lib/types";

const stageLabelMap: Record<string, string> = {
  stage_one: "第一阶段",
  stage_two: "第二阶段"
};

const stageStartedMap: Record<string, string> = {
  stage_one: "第一阶段审查已启动。",
  stage_two: "第二阶段审查已启动。"
};

const stageRunningMap: Record<string, string> = {
  stage_one: "正在分析权利要求书并提取关键技术特征。",
  stage_two: "正在核对说明书、附图和摘要的支持情况。"
};

const stageCompletedMap: Record<string, string> = {
  stage_one: "第一阶段检查完成，准备核对说明书支持情况。",
  stage_two: "第二阶段检查完成，正在整理最终报告。"
};

export function formatPatentEventStage(stage: string) {
  return stageLabelMap[stage] ?? "审查过程";
}

export function formatPatentEventMessage(event: PatentCheckEvent) {
  if (!isTechnicalEventMessage(event.message)) {
    return event.message;
  }
  if (event.event_type === "thread.started") {
    return stageStartedMap[event.stage] ?? "审查任务已启动。";
  }
  if (event.event_type === "turn.started") {
    return stageRunningMap[event.stage] ?? "正在执行审查任务。";
  }
  if (event.event_type === "turn.completed") {
    return stageCompletedMap[event.stage] ?? "阶段审查已完成。";
  }
  if (event.event_type === "item.started") {
    return "正在准备审查规则和任务材料。";
  }
  if (event.event_type === "item.completed") {
    return "正在生成阶段审查结果。";
  }
  if (event.event_type === "error") {
    return "模型服务连接不稳定，系统正在自动重试。";
  }
  return stageRunningMap[event.stage] ?? "正在执行审查任务。";
}

function isTechnicalEventMessage(message: string) {
  return (
    message.startsWith("Codex ") ||
    message.startsWith("Codex 事件") ||
    message.includes("item.") ||
    message.includes("turn.") ||
    message.includes("thread.") ||
    message.includes("stage_")
  );
}
