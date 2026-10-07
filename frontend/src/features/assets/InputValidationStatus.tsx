import { useEffect, useState } from "react";
import { usePageActivity } from "../../shared/hooks/usePageActivity";
import { listProjectAssets, listProjectDatasets } from "../../shared/api/projects";
import { getAssetSetName, projectAssetDetailPath } from "./assetSets";

type Row = { id: string; name: string; status: string; message: string; assetSet: string };
const labels: Record<string, string> = { valid: "校验通过", pending: "等待校验", invalid: "校验未通过", needs_mapping: "需要确认列映射", unknown: "首次使用时校验", failed: "校验失败" };
export function InputValidationStatus({ projectId, revision, assetSet = "", active = true }: { projectId: string; revision: number; assetSet?: string; active?: boolean }) {
  const pageActive = usePageActivity(active);
  const [rows, setRows] = useState<Row[]>([]);
  const [expanded,setExpanded]=useState(false);
  const [total, setTotal] = useState(0);
  const [states, setStates] = useState<Record<string, number>>({});
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!pageActive) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const [summary, result] = await Promise.all([
          listProjectDatasets(projectId, {skipCache:true}),
          expanded ? listProjectAssets(projectId, { inputsOnly: true, assetSet, pageSize: 20, skipCache: true }) : Promise.resolve({assets:[]}),
        ]);
        if (!active) return;
        const counts: Record<string, number> = {};
        for (const dataset of summary.datasets.filter(item => !assetSet || item.name === assetSet))
          for (const kind of Object.values(dataset.kinds)) for (const [status, count] of Object.entries(kind.statuses)) counts[status] = (counts[status] || 0) + count;
        setStates(counts); setTotal(summary.datasets.filter(item=>!assetSet || item.name===assetSet).reduce((count,dataset)=>count+dataset.input_count,0));
        setRows(result.assets.map(asset => { const validation = (asset.metadata as Record<string, any> | undefined)?.validation || {};
          return { id: asset.id, name: asset.original_name, assetSet: getAssetSetName(asset), status: validation.status || "unknown", message: (validation.summary?.errors || []).join("；") || validation.message || "" }; }));
        setError("");
        if (counts.pending) timer = setTimeout(load, 5000);
      } catch { if (active) setError("校验状态暂时无法读取，请点击重新读取。"); }
    }
    load();
    return () => { active = false; clearTimeout(timer); };
  }, [projectId, revision, assetSet, retry, expanded, pageActive]);
  return <div aria-live="polite">{error && <p role="alert">{error}<button className="btn btn-secondary" onClick={() => setRetry(value => value + 1)}>重新读取</button></p>}
    {total > 0 && <details open={expanded} onToggle={event=>setExpanded(event.currentTarget.open)}><summary onClick={event=>{event.preventDefault();setExpanded(value=>!value);}}>{assetSet ? `${assetSet} · ` : ""}{total} 个输入文件 · 查看校验状态</summary>
      <p className="data-muted">{Object.entries(states).map(([state,count]) => `${labels[state] || "尚未校验"} ${count} 个`).join(" · ")}</p>
      <ul>{rows.map(row => <li key={row.id}><a href={projectAssetDetailPath(projectId, row.id, row.assetSet)}>{row.name}</a> · {labels[row.status] || "尚未校验"}{row.message && <p>{row.message}</p>}</li>)}</ul>
      <a href={`/management/projects/${projectId}?tab=assets&asset_set=${encodeURIComponent(assetSet)}`}>{total > rows.length ? "查看完整文件列表" : "查看文件与校验详情"}</a></details>}
  </div>;
}
