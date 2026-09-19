import { apiClient } from "./client";
import type { UploadedFile } from "./files";
export interface SchemeField { field: string; display_name?: string; mapping_hints?: string[]; }
export interface AnalysisScheme { id: string; name: string; description: string; required_fields?: SchemeField[]; optional_fields?: SchemeField[]; }
export const listAnalysisSchemes = () => apiClient.get<{ schemes: AnalysisScheme[] }>("/api/analysis/schemes");
export const getAnalysisScheme = (id: string) => apiClient.get<AnalysisScheme>(`/api/analysis/schemes/${encodeURIComponent(id)}`);
export function unifiedPayload(file: UploadedFile | null, mode: "scheme" | "custom", scheme: AnalysisScheme | null, mapping: Record<string,string>, fields: string[], sample: string, baseline: string) {
  if (!file) throw new Error("请先上传或选择数据文件。");
  const payload: Record<string, unknown> = { file_id: file.id, mode };
  if (mode === "scheme") {
    if (!scheme) throw new Error("请选择已加载的分析方案。");
    for (const field of scheme.required_fields || []) if (!file.columns.includes(mapping[field.field])) throw new Error(`请映射必需字段：${field.display_name || field.field}`);
    const fieldMapping = Object.fromEntries(Object.entries(mapping).filter(([, column]) => !!column));
    if (Object.values(fieldMapping).some(column => !file.columns.includes(column))) throw new Error("映射列不在当前文件中，请重新选择。");
    if (new Set(Object.values(fieldMapping)).size !== Object.values(fieldMapping).length) throw new Error("同一数据列不能映射到多个标准字段。");
    payload.scheme_id = scheme.id;
    payload.field_mapping = fieldMapping;
    payload.parameters = baseline ? { baseline_sample: baseline } : {};
  } else {
    if (!sample || !file.columns.includes(sample)) throw new Error("请选择样本标识列。");
    if (!fields.length || fields.some(field => !file.columns.includes(field) || field === sample)) throw new Error("请选择当前文件中的指标列，并排除样本标识列。");
    payload.selected_fields = fields;
    payload.parameters = { sample_column: sample, baseline_sample: baseline || null };
  }
  return { module: "analysis.execute-unified", payload };
}
