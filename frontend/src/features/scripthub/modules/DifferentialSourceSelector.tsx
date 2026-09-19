import { useEffect, useState } from "react";
import { apiClient } from "../../../shared/api/client";
import type { ScriptHubSourceContext } from "../../jobs/forms";
import { Field, inputStyle } from "./shared";

type Source = {id: string; status: string; reason?: string; created_at?: string; metadata: {pvalue_threshold?: number; logfc_cutoff?: number; comparisons?: Array<{group1: string; group2: string}>}};
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
    apiClient.get<{candidates: Source[]}>("/api/script-hub/go-kegg-enrichment/sources", {project_id: projectId, asset_set: assetSet}, {skipCache: true})
      .then(result => {if (active) setSources(result.candidates);})
      .catch(reason => {if (active) setError(reason instanceof Error ? reason.message : "差异结果读取失败");})
      .finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
  }, [projectId, assetSet, retry]);
  const selected = sources.find(source => source.id === value);
  return <div>
    <p>沿用来源分析的比较组合、差异筛选标记和统计值，不重新计算差异表达。</p>
    {!projectId || !assetSet ? <p>请先选择项目和数据集。</p> : <>
      {loading && <p role="status">正在读取差异表达结果…</p>}
      {error && <p role="alert">{error} <button type="button" className="btn btn-secondary" onClick={() => setRetry(count => count + 1)}>重新读取</button></p>}
      {!loading && !error && sources.length === 0 && <p>当前数据集尚无可用差异结果，请先完成差异表达分析。</p>}
      <Field label="来源差异表达结果"><select aria-label="来源差异表达结果" style={inputStyle} value={value} disabled={loading || !!error} onChange={event => onSelect(event.target.value)}>
        <option value="">请选择来源结果</option>
        {sources.map(source => <option key={source.id} value={source.id} disabled={source.status !== "available"}>
          {(source.metadata.comparisons || []).map(pair => `${pair.group1} 与 ${pair.group2}`).join("、") || "差异表达分析"} · {source.created_at?.replace("T", " ").slice(0, 19) || "历史任务"}{source.reason ? ` · ${source.reason}` : ""}
        </option>)}
      </select></Field>
      {value && !loading && !error && (!selected || selected.status !== "available") && <p role="alert">所选来源当前不可用，请重新选择。</p>}
      {selected?.status === "available" && <p>上游 p 值阈值：{selected.metadata.pvalue_threshold ?? "未记录"}；对数倍数变化阈值：{selected.metadata.logfc_cutoff ?? "未记录"}。</p>}
    </>}
  </div>;
}
