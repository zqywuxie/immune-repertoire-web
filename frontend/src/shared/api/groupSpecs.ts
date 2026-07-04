/** Group-spec API for ScriptHub analysis module forms. */
import { apiClient } from "./client";

export interface GroupSpec {
  id: string;
  name: string;
  project_id: string;
  spec_json?: Record<string, unknown>;
}

export interface GroupSpecListResponse {
  group_specs: GroupSpec[];
}

export function listGroupSpecs(projectId: string) {
  return apiClient.get<GroupSpecListResponse>(
    `/api/projects/${projectId}/group-specs`
  );
}
