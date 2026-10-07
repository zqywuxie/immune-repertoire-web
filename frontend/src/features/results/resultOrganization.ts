import type { ResultOutput } from "./ResultViewer";

export type BrowseOutput = ResultOutput & { key: string };
export type ResultComparison = { key: string; label: string; filenames: string[] };
export type OrganizedOutput = BrowseOutput & { content: string; chains: string[]; comparison: string };
const chains = ["TRA", "TRB", "TRG", "TRD", "IGH", "IGK", "IGL"];

function filenameText(output: ResultOutput) {
  let pathname = output.url.split("?")[0];
  try { pathname = new URL(output.url, "http://result.local").pathname; } catch { /* Relative filenames remain searchable. */ }
  pathname = pathname.replace(/^\/api\/script-hub\/results\/[^/]+\//, "/");
  try { pathname = decodeURIComponent(pathname); } catch { /* Keep malformed historical paths readable. */ }
  return { pathname, text: pathname + " " + String(output.label || "") };
}

export function resultComparisons(result: unknown): ResultComparison[] {
  const data = result && typeof result === "object" ? result as Record<string, unknown> : {};
  const metadata = data.metadata && typeof data.metadata === "object" ? data.metadata as Record<string, unknown> : {};
  const rows = [data.comparisons, data.comparison_sample_counts, metadata.comparisons, metadata.comparison_sample_counts].flatMap(value => Array.isArray(value) ? value : []);
  const found = new Map<string, ResultComparison>();
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const left = String(row.group1 || ""), right = String(row.group2 || "");
    if (!left || !right) continue;
    const key = JSON.stringify([left, right]);
    // These are the existing Volcano/CSR and TopClone filename encodings.
    const safe = (value: string) => value.replace(/[^\p{L}\p{N}_.-]+/gu, "_").replace(/^_+|_+$/g, "");
    const ascii = (value: string) => value.replace(/[^A-Za-z0-9_.-]+/g, "_").replace(/^[._]+|[._]+$/g, "") || "group";
    found.set(key, { key, label: left + " 与 " + right, filenames: [...new Set([safe(left) + "_vs_" + safe(right), ascii(left) + "_vs_" + ascii(right)])] });
  }
  return [...found.values()];
}

export function organizeOutput(output: BrowseOutput, comparisons: ResultComparison[] = []): OrganizedOutput {
  const { pathname, text } = filenameText(output), lower = text.toLowerCase();
  const matchedChains = chains.filter(chain => new RegExp("(^|[^A-Za-z0-9])" + chain + "(?=$|[^A-Za-z0-9])", "i").test(text));
  const matchedComparisons = comparisons.filter(comparison => comparison.filenames.some(name => {
    const escaped = name.replace(/[.*+?^$()|[\]{}\\]/g, "\\$&");
    return new RegExp("(^|[/_\\s])" + escaped + "(?=$|[/_\\s.])").test(text);
  }));
  let comparison = matchedComparisons.length === 1 ? matchedComparisons[0].key : "";
  if (!comparisons.length) {
    // An entire directory segment is an explicit comparison; a filename alone may also contain metric names.
    const segment = pathname.split("/").slice(0, -1).find(part => part.includes("_vs_"));
    if (segment) comparison = "directory:" + segment;
  }
  let content = "其他结果";
  if (output.kind === "html") content = "交互报告";
  else if (/csr_|类别转换/.test(lower)) content = "类别转换";
  else if (/受体链构成|免疫球蛋白亚类构成/.test(text)) content = "组成与比例";
  else if (/volcano|differential|差异|火山/.test(lower)) content = "差异比较";
  else if (/umap/.test(lower)) content = "降维与样本分布";
  else if (/vjusage|vusage|jusage|基因使用频率/.test(lower)) content = "基因使用频率";
  else if (/pep_shared|shared_matrix|clone_tracking|克隆共享/.test(lower)) content = "克隆共享";
  else if (/topclone|top_clone|优势克隆/.test(lower)) content = "优势克隆";
  else if (/shannon|simpson|chao1|diversity|多样性/.test(lower)) content = "多样性";
  else if (/infiltration|concordance|浸润|一致性/.test(lower)) content = "免疫浸润与一致性";
  else if (/gsea|kegg|enrichment|富集/.test(lower)) content = "通路与富集";
  else if (output.kind === "pdf") content = "图表与文档";
  else if (output.category && !["图表", "图像", "已登记结果", "数据表", "统计表", "PNG", "PDF"].includes(output.category)) content = output.category;
  return { ...output, content, chains: matchedChains, comparison };
}

export function comparisonLabel(key: string, comparisons: ResultComparison[]) {
  return comparisons.find(item => item.key === key)?.label || key.replace(/^directory:/, "").replace("_vs_", " 与 ");
}
