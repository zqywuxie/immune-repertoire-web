import type { components } from "./generated/schema";
import { apiClient } from "./client";

export type SampleBatchPreviewRow = components["schemas"]["SampleBatchPreviewRow"];
export type SampleBatchPreview = components["schemas"]["SampleBatchPreview"];
export type SampleBatchResultRow = components["schemas"]["SampleBatchResultRow"];
export type SampleBatchResult = components["schemas"]["SampleBatchResult"];
export type SampleBatchInput = components["schemas"]["SampleBatchInput"];
const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const path = (projectId: string) => `/api/projects/${encodeURIComponent(projectId)}/samples/batch`;

async function errorMessage(response: Response) {
  const content = await response.json().catch(() => ({}));
  return typeof content.message === "string" ? content.message : "批量登记请求失败，请重试。";
}
export async function downloadSampleBatchTemplate(projectId: string, assetSet: string, recordIds?: string[]) {
  const response = await fetch(`${base}${path(projectId)}/template`, { method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ asset_set: assetSet, record_ids: recordIds }) });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.blob();
}
export async function previewSampleBatchFile(projectId: string, assetSet: string, file: File, allowUnmatched: boolean, recordIds?: string[]) {
  const data = new FormData(); data.set("asset_set", assetSet); data.set("allow_unmatched", String(allowUnmatched)); data.set("file", file);
  if (recordIds) data.set("record_ids", JSON.stringify(recordIds));
  const response = await fetch(`${base}${path(projectId)}/preview`, { method: "POST", credentials: "include", body: data });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json() as Promise<SampleBatchPreview>;
}
export function previewSampleBatchRows(projectId: string, assetSet: string, rows: SampleBatchInput[]) {
  return apiClient.post<SampleBatchPreview>(`${path(projectId)}/preview`, { asset_set: assetSet, rows });
}
export function applySampleBatch(projectId: string, previewToken: string, rows: number[]) {
  return apiClient.post<SampleBatchResult>(`${path(projectId)}/apply`, { preview_token: previewToken, rows });
}
