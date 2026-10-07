const speciesAliases: Record<string, string> = {human:"human", "人":"human", "人类":"human", "homo sapiens":"human",mouse:"mouse", "小鼠":"mouse", "mus musculus":"mouse",other:"other", "其他":"other"};
export function canonicalSpecies(value: string) { return speciesAliases[value.trim().toLowerCase()] || value; }
export function speciesLabel(value: string | null | undefined) {
  if (!value) return "未设置";
  const key=canonicalSpecies(value);
  return ({human:"人",mouse:"小鼠",other:"其他"} as Record<string,string>)[key] || value;
}
export function speciesOptions(values: string[]) {
  return [...new Set(["human","mouse","other",...values.map(canonicalSpecies)])].map(value=>({value,label:speciesLabel(value)}));
}
export function healthyLabel(value: string | null | undefined) { return value === "yes" ? "健康" : value === "no" ? "非健康" : value || "未设置"; }
export function pairedLabel(value: string | null | undefined) { return value === "yes" ? "是" : value === "no" ? "否" : value || "未设置"; }

export const sampleFieldLabels: Record<string, string> = {
  sample_name: "样本名称", sequence_id: "序列编号", chain_flag: "链标记", is_healthy: "健康状态",
  is_pe: "双端测序", spices: "物种", illness: "疾病", institution: "所属机构",
  contain_method: "纳入方法", iso_tag: "同型标签",
};
export function registrationSource(metadata: Record<string, unknown> | null | undefined): string {
  if (metadata?.source_asset_id) return "来源表导入";
  if (metadata?.registration_kind === "manual") return metadata.unmatched_input ? "人工补充（尚未关联输入）" : "人工补充";
  return "来源未记录";
}
export function manuallyMaintainedFields(metadata: Record<string, unknown> | null | undefined): string[] {
  return Array.isArray(metadata?.manual_fields) ? metadata.manual_fields.filter((value): value is string => typeof value === "string") : [];
}
