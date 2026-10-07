import { useEffect, useState } from "react";
import { apiClient } from "../../../shared/api/client";
import type { ScriptHubSourceContext } from "../../jobs/forms";
import { Field, inputStyle } from "./shared";
import {SourceTaskLink,formatSourceTime} from "./SourceSelection";

type Source = {id: string; job_id?: string; files?: unknown[]; status: string; reason?: string; created_at?: string; metadata: {output_name?: string; sample_count?: number; selected_expression_samples?: string[]; significance_column?: string; pvalue_threshold?: number; logfc_cutoff?: number; comparisons?: Array<{group1: string; group2: string}>}};
export function DifferentialSourceSelector({sourceContext, value, onSelect}: {sourceContext?: ScriptHubSourceContext; value: string; onSelect: (id: string) => void}) {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const projectId = sourceContext?.projectId;
  const assetSet = sourceContext?.assetSetId;
  useEffect(() => {
    let active = true;
    setSources([]); setError("");
    if (!projectId || !assetSet) { setLoading(false); return; }
    setLoading(true);
    apiClient.get<{candidates: Source[]}>("/api/script-hub/go-kegg-enrichment/sources", {project_id: projectId, asset_set: assetSet}, {skipCache: true, deduplicate: false})
      .then(result => {if (active) setSources(result.candidates || []);})
      .catch(reason => {if (active) setError(reason instanceof TypeError ? "网络连接中断，请重新读取。" : reason instanceof Error ? reason.message : "差异结果读取失败");})
      .finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
  }, [projectId, assetSet, retry]);
  const selected = sources.find(source => source.id === value);
  const available = sources.filter(source => source.status === "available");
  const upstreamQuery = new URLSearchParams();
  if (projectId) upstreamQuery.set("project", projectId);
  if (assetSet) upstreamQuery.set("asset_set", assetSet);
  return <section className="source-selection" aria-label="差异表达来源选择" aria-busy={loading}>
    <p>沿用来源分析的比较组合、差异筛选标记和统计值，不重新计算差异表达。</p>
    {!projectId || !assetSet ? <p>请先选择项目和数据集。</p> : <>
      <div className="source-selection-actions">
        <span>{loading ? "正在读取差异表达结果…" : error ? "来源读取未完成" : available.length+"/"+sources.length+" 项来源可用"}</span>
        <button type="button" className="btn btn-secondary" disabled={loading} onClick={() => setRetry(count => count + 1)}>刷新差异来源</button>
      </div>
      {loading && <p role="status">正在核对当前项目和数据集的来源…</p>}
      {error && <div role="alert" className="source-selection-message"><p>差异结果读取失败：{error}</p><button type="button" className="btn btn-secondary" onClick={() => setRetry(count => count + 1)}>重新读取差异来源</button></div>}
      {!loading && !error && !available.length && <div className="source-selection-message">
        <p>{sources.length ? "已有来源目前均不可用，请查看来源原因或重新运行。" : "当前数据集尚无可用差异结果，请先完成差异表达分析。"}</p>
        <a className="source-task-link" href={"/analysis/tools/expression?" + upstreamQuery} target="_blank" rel="noreferrer">前往差异表达分析 ↗</a>
      </div>}
      <Field label="来源差异表达结果"><select aria-label="来源差异表达结果" style={inputStyle} value={selected ? value : ""} disabled={loading || !!error} onChange={event => onSelect(event.target.value)}>
        <option value="">请选择来源结果</option>
        {sources.map(source => <option key={source.id} value={source.id} disabled={source.status !== "available"}>
          {source.metadata.output_name || "差异表达分析"} · {(source.metadata.comparisons || []).map(pair => pair.group1+" 与 "+pair.group2).join("、") || "未记录比较"} · {formatSourceTime(source.created_at)} · {source.job_id || source.id}{source.reason ? " · "+source.reason : ""}
        </option>)}
      </select></Field>
      {value && !loading && !error && (!selected || selected.status !== "available") && <p role="alert">所选来源当前不可用，请重新选择。</p>}
      {selected && !loading && !error && <div className="source-selection-message">
        <strong>{selected.metadata.output_name || "来源差异表达分析"}</strong>
        <div style={{color:"var(--text-secondary)",fontSize:".8rem",marginTop:8,lineHeight:1.8}}>
          <div>来源任务：{selected.job_id || selected.id}</div>
          <div>创建时间：{formatSourceTime(selected.created_at)}</div>
          {selected.status !== "available" ? <p>{selected.reason || "来源当前不可用。"}</p> : <>
            <div>归一化样本：{selected.metadata.sample_count ?? "未记录"}；比较组合：{selected.metadata.comparisons?.length ?? "未记录"}；完整差异表：{selected.files?.length ?? "未记录"}</div>
            <div>比较方向：{(selected.metadata.comparisons || []).map(pair => pair.group1+" / "+pair.group2).join("、") || "未记录"}</div>
            <div>来源筛选：{selected.metadata.significance_column === "significant_fdr" ? "BH-FDR" : selected.metadata.significance_column === "significant_raw" ? "原始 P 值" : "沿用来源筛选标记"}；阈值：{selected.metadata.pvalue_threshold ?? "未记录"}；对数倍数变化阈值：{selected.metadata.logfc_cutoff ?? "未记录"}</div>
            {selected.metadata.selected_expression_samples?.length ? <details><summary>查看来源实际样本列</summary><div className="source-selection-samples">{selected.metadata.selected_expression_samples.join("、")}</div></details> : null}
          </>}
        </div>
        <SourceTaskLink jobId={selected.job_id} projectId={projectId} assetSet={assetSet}/>
      </div>}
    </>}
  </section>;
}
