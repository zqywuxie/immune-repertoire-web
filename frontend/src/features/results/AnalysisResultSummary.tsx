import type {JobResultsResponse} from "../../shared/api/jobs";
import {assetTypeLabels} from "../assets/assetLabels";
import "./AnalysisResultSummary.css";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function count(value: unknown) {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}
function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function AnalysisResultSummary({result}: {result: JobResultsResponse}) {
  if (result.status !== "completed") return null;
  const metadata = record(result.result.metadata);
  const payload = record(result.job.payload);
  const job = record(result.job);
  const inputs = Array.isArray(job.input_assets) ? job.input_assets : Array.isArray(payload.input_assets) ? payload.input_assets : [];
  const sources = inputs.map(record);
  const samples = count(metadata.sample_count);
  const selected = count(metadata.selected_sample_count);
  const unmatched = count(metadata.excluded_unmatched_sample_count);
  const unused = strings(metadata.unused_selected_samples);
  const chains = strings(metadata.selected_chains ?? metadata.chains);
  const warnings = strings(metadata.warnings);
  const notes = strings(metadata.analysis_notes);
  const comparisons = Array.isArray(metadata.comparison_sample_counts) ? metadata.comparison_sample_counts.map(record) : [];
  const group = [metadata.group_field, metadata.group_column, metadata.label_col].find(value => typeof value === "string" && value);
  const outputs = Array.isArray(result.outputs) ? result.outputs : [];
  const figures = outputs.filter(output => ["image", "png", "svg", "pdf", "html"].includes(output.kind)).length;
  const tables = outputs.filter(output => ["table", "csv", "tsv", "xlsx"].includes(output.kind)).length;
  return <section className="analysis-result-summary" aria-label="本次分析概览">
    <div className="analysis-result-summary__heading"><strong>本次分析概览</strong><span>依据本任务保存的记录</span></div>
    <dl className="analysis-result-summary__facts">
      <div><dt>数据集</dt><dd>{typeof payload.asset_set === "string" && payload.asset_set || "未记录"}</dd></div>
      <div><dt>{samples !== null ? "纳入样本" : selected !== null ? "所选样本" : "样本数量"}</dt><dd>{samples !== null ? `${samples} 个` : selected !== null ? `${selected} 个（所选范围）` : "本任务未记录"}</dd></div>
      {!!group && <div><dt>分组字段</dt><dd>{String(group)}</dd></div>}
      {!!chains.length && <div><dt>受体链</dt><dd>{chains.join(" / ")}</dd></div>}
      <div><dt>已登记输出</dt><dd>{outputs.length} 项{figures || tables ? ` · 图表或报告 ${figures} · 数据表 ${tables}` : ""}</dd></div>
    </dl>
    {(unmatched !== null || unused.length > 0 || (samples !== null && selected !== null && selected !== samples)) && <p className="analysis-result-summary__note">
      {samples !== null && selected !== null && selected !== samples ? `所选范围 ${selected} 个样本，实际纳入 ${samples} 个。` : ""}
      {unmatched !== null ? `未匹配输入而排除 ${unmatched} 个样本。` : ""}
      {unused.length > 0 ? `未参与本次比较的所选样本：${unused.join("、")}。` : ""}
    </p>}
    {comparisons.length > 0 && <details><summary>比较方向与样本数量（{comparisons.length}）</summary><ul>{comparisons.map((comparison,index) => <li key={index}>
      {String(comparison.group1 || "未记录")} / {String(comparison.group2 || "未记录")}：前组 {count(comparison.group1_n) ?? "未记录"}，后组 {count(comparison.group2_n) ?? "未记录"} 个样本
    </li>)}</ul></details>}
    {sources.length > 0 && <details><summary>本次保存的输入版本（{sources.length}）</summary><ul>{sources.map((source,index) => {
      const project = result.job.project_id;
      const id = typeof source.asset_id === "string" ? source.asset_id : "";
      const scope = typeof source.asset_set === "string" ? source.asset_set : typeof payload.asset_set === "string" ? payload.asset_set : "";
      const type = typeof source.asset_type === "string" ? source.asset_type : "input";
      const name = typeof source.name === "string" ? source.name : typeof source.path === "string" ? source.path.split(/[\\/]/).pop() : "";
      return <li key={`${id}:${index}`}><strong>{assetTypeLabels[type] || "分析输入"} · {name || id || "未记录文件名"}</strong>
        <p>{source.content_version ? `执行时版本：${String(source.content_version)}` : "未记录内容版本；请通过分析记录核对执行时文件信息。"}</p>
        {!!id && !!project && <a href={`/management/projects/${encodeURIComponent(project)}?${new URLSearchParams({tab:"assets",asset_set:scope,asset:id})}`} target="_blank" rel="noreferrer">查看对应输入登记</a>}
      </li>;
    })}</ul><p className="analysis-result-summary__note">以上为执行时快照。对应输入登记的当前状态可能已更新。</p></details>}
    {!!warnings.length && <div role="status" className="analysis-result-summary__warnings"><strong>结果注意事项</strong><ul>{warnings.map((warning,index) => <li key={index}>{warning}</li>)}</ul></div>}
    {!!notes.length && <details><summary>方法与统计说明</summary><ul>{notes.map((note,index) => <li key={index}>{note}</li>)}</ul></details>}
  </section>;
}
