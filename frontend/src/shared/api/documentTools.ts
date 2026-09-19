import { apiClient } from './client';
export async function uploadDocument<T>(path: string, file: File, project?: string): Promise<T> {
  const form = new FormData(); form.append('file', file); if (project) form.append('project', project);
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}${path}`, { method: 'POST', credentials: 'include', body: form });
  const data = await response.json();
  if (!response.ok || data.success === false) throw new Error(data.message || data.error || '文件处理失败');
  return data;
}
export async function documentAction<T>(path: string, payload: unknown): Promise<T> {
  const data = await apiClient.post<T & { success?: boolean; error?: string; message?: string }>(path,payload);
  if (data.success === false) throw new Error(data.message || data.error || '处理失败');
  return data;
}
