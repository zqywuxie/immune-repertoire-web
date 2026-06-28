export type ProjectStatus = "active" | "archived" | "paused" | string;

export interface ProjectSummary {
  id: string;
  name: string;
  institution?: string | null;
  cooperation_level?: string | null;
  description?: string | null;
  status: ProjectStatus;
  created_at?: string | null;
  updated_at?: string | null;
  asset_counts?: Record<string, number>;
  result_count?: number;
  sample_count?: number;
  group_spec_count?: number;
}

export interface ProjectAsset {
  id: string;
  project_id: string;
  asset_type: string;
  original_name: string;
  storage_path: string;
  storage_uri?: string | null;
  mime_type?: string | null;
  size: number;
  metadata?: Record<string, unknown>;
  uploaded_at?: string | null;
}

export interface JobSummary {
  id: string;
  job_id?: string;
  job_type: string;
  module: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | string;
  progress: number;
  stage?: string | null;
  detail?: string | null;
  project_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

export interface JobModule {
  key: string;
  label: string;
}

export interface JobOutput {
  label: string;
  url: string;
  kind: string;
}
