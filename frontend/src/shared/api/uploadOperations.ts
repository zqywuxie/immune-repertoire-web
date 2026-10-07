import { apiClient } from "./client";
import type { ProjectAsset } from "../types/domain";

export class UploadResponseUnknownError extends Error {
  constructor(message = "保存状态暂时无法确认；文件选择已保留，重试前会核对保存结果。") {
    super(message);
    this.name = "UploadResponseUnknownError";
  }
}

export function createUploadOperationId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // Internal servers may use HTTP, where randomUUID is unavailable.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function getSavedUploadOperation(projectId: string, operationId: string) {
  return apiClient.get<{ saved: boolean; assets: ProjectAsset[] }>(
    `/api/projects/${encodeURIComponent(projectId)}/upload-operations/${encodeURIComponent(operationId)}`,
    undefined, { skipCache: true });
}

export async function confirmInterruptedUpload(projectId: string, operationId: string) {
  try {
    const result = await getSavedUploadOperation(projectId, operationId);
    if (result.saved) return { assets: result.assets };
  } catch { /* Keep uncertain items available for a safe retry with the same identity. */ }
  throw new UploadResponseUnknownError();
}
