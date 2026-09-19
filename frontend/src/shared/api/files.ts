import { apiClient } from "./client";

export interface UploadedFile { id: string; name: string; columns: string[]; row_count: number; }
export async function uploadDataFile(file: File, project: string): Promise<UploadedFile> {
  const body = new FormData();
  body.append("file", file, file.name);
  body.append("project", project);
  const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
  const response = await fetch(`${base}/api/files/upload`, { method: "POST", credentials: "include", body });
  const data = await response.json();
  if (!response.ok || !data.id) throw new Error(data.message || data.error || "文件上传失败");
  apiClient.invalidatePath("/api/files");
  return data;
}


export const listDataFiles = (project: string) => apiClient.get<{ files: UploadedFile[] }>("/api/files", { project });
