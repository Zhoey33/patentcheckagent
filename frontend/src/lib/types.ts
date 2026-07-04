// 这个文件用于定义前端与后端接口共享的数据类型。

export type User = {
  id: string;
  username: string;
  role: "user" | "admin";
  is_active: boolean;
};

export type PatentCheckFile = {
  id: string;
  file_role: string;
  original_filename: string;
  content_type: string | null;
  file_size_bytes: number;
  extracted_text_length: number;
  extraction_status: string;
  extraction_error: string | null;
  created_at: string;
};

export type PatentCheckProgressStep = {
  key: string;
  label: string;
  status: "pending" | "running" | "done" | "failed" | string;
};

export type PatentCheckTask = {
  id: string;
  title: string;
  technical_field: string | null;
  status: string;
  claims_text_length: number;
  specification_text_length: number;
  drawings_text_length: number;
  abstract_text_length: number;
  input_cleanup_status: string;
  progress_stage: string;
  progress_percent: number;
  progress_message: string;
  progress_steps: PatentCheckProgressStep[];
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  files: PatentCheckFile[];
};

export type PatentCheckTaskList = {
  items: PatentCheckTask[];
  total: number;
  page: number;
  page_size: number;
};

export type PatentCheckReport = {
  id: string;
  status: string;
  progress_stage: string;
  progress_percent: number;
  progress_message: string;
  progress_steps: PatentCheckProgressStep[];
  final_report: string | null;
  error_message: string | null;
};

export type PatentCheckEvent = {
  id: number;
  task_id: string;
  stage: string;
  event_type: string;
  message: string;
  content: string | null;
  created_at: string;
};

export type PatentCheckEventList = {
  items: PatentCheckEvent[];
};
