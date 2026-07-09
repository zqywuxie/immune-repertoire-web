/**
 * Domain types — re-exported from auto-generated OpenAPI schema.
 *
 * When the OpenAPI spec is updated, run ``npm run generate-types`` and
 * these re-exports pick up the changes automatically.  Any types not yet
 * in the OpenAPI spec are defined inline below.
 *
 * Migration note (2026-06-30):
 *   These were previously hand-written and have been replaced by
 *   generated aliases from ``../api/generated/helpers``.
 */

export type {
  Project as ProjectSummary,
  ProjectDetail,
  ProjectCreate,
  ProjectUpdate,
  ProjectStatus,
  Asset as ProjectAsset,
  Job as JobSummary,
  JobStatus,
  JobOutput,
  Pagination,
} from "../api/generated/helpers";

// ── Types not yet in OpenAPI spec ────────────────────────────────────

/** Module catalog entry (will move to generated types when spec updated). */
export interface JobModule {
  key: string;
  label: string;
  category?: string;
  description?: string;
  output_kinds?: string[];
  ui_entry?: string;
  execution_mode?: "job" | "script-hub-legacy";
  status?: string;
}
