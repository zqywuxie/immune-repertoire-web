import type { UploadedFile as StatisticalFile } from "./files";

export function statisticalPayload(files: StatisticalFile[], value: string, group: string, kind: "statistics" | "boxplot") {
  if (!files.length) throw new Error("请先上传数据文件。");
  if (!value || !group || value === group) throw new Error("请选择不同的数值列和分组列。");
  if (files.some(file => !file.columns.includes(value) || !file.columns.includes(group))) throw new Error("所选字段必须存在于每个文件中。");
  if (new Set(files.map(file => file.name)).size !== files.length) throw new Error("多个文件名称重复，请重命名后上传，避免结果覆盖。");
  const single = files.length === 1;
  const module = kind === "boxplot" ? (single ? "statistical.boxplot" : "statistical.summary-boxplot") : (single ? "statistical.analyze" : "statistical.analyze-multiple");
  return { module, payload: { value_column: value, group_column: group, ...(single ? { file_id: files[0].id } : { files: files.map(file => ({ file_id: file.id, name: file.name })) }) } };
}
