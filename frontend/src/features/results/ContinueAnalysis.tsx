import { apiClient } from "../../shared/api/client";
import { useEffect, useState } from "react";
import type { JobResultsResponse } from "../../shared/api/jobs";
import { listPepCacheCandidates, type PepCacheCandidate } from "../../shared/api/scriptHub";

export function ContinueAnalysis({ result }: { result: JobResultsResponse }) {
  const job = result.job as unknown as Record<string, unknown>;
  const payload = (job.payload || {}) as Record<string, unknown>;
  const project = String(job.project_id || "");
  const dataset = String(payload.asset_set || "");
  const task = String(job.job_id || job.id || "");
  const differential = [job.module, job.job_type].includes("volcano");
  const enabled = result.status === "completed" && ([job.module, job.job_type].includes("pep-analysis") || differential) && !!project && !!dataset && !!task;
  const [candidates, setCandidates] = useState<PepCacheCandidate[]>([]);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let disposed = false;
    setCandidates([]);
    setError("");
    if (!enabled) return;
    if (differential) {
      apiClient.get<{candidates:Array<{id:string;job_id:string;status:string}>}>("/api/script-hub/go-kegg-enrichment/sources", {project_id:project,asset_set:dataset}, {skipCache:true}).then(response => {
        if (!disposed) setCandidates(response.candidates.filter(item => item.status === "available" && item.job_id === task).map(item => ({...item, artifact_id:item.id, cache_type:"deg", label:"本次差异表达结果", path:""} as PepCacheCandidate)));
      }).catch(reason => { if (!disposed) setError(reason instanceof Error ? reason.message : "无法读取后续分析入口"); });
      return () => { disposed = true; };
    }
    listPepCacheCandidates(project, undefined, dataset).then(response => {
      if (!disposed) setCandidates(response.candidates.filter(item => item.status === "available" && item.job_id === task && item.artifact_id));
    }).catch(reason => { if (!disposed) setError(reason instanceof Error ? reason.message : "无法读取后续分析入口"); });
    return () => { disposed = true; };
  }, [enabled, differential, project, dataset, task, revision]);
  if (!enabled || (!candidates.length && !error)) return null;
  return <section aria-label="继续分析" style={{ display: "grid", gap: "var(--spacing-sm)" }}>
    <h3 style={{ margin: 0 }}>使用本次结果继续分析</h3>
    <p style={{ margin: 0, color: "var(--text-secondary)" }}>保留当前项目和数据集，进入配置后确认参数再运行。</p>
    {error && <div role="alert">{error} <button className="btn btn-secondary" onClick={() => setRevision(value => value + 1)}>重新读取</button></div>}
    {candidates.map(candidate => {
      const targets = candidate.cache_type === "deg" ? [["go-kegg", "GO / KEGG 富集"]] : candidate.cache_type === "vj_usage" ? [["vj-difference", "V/J 使用差异"], ["umapin", "UMAP 特征降维"], ["ml", "机器学习"]]
        : candidate.cache_type === "umapin_table" ? [["umapin", "UMAP 特征降维"], ["ml", "机器学习"]]
        : candidate.cache_type === "tra_shared" ? [["mait-nkt", "MAIT / NKT 特征"]] : [];
      if (!targets.length) return null;
      return <div key={candidate.artifact_id} style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)", alignItems: "center" }}>
        <span>{candidate.label || "前置结果"}{candidate.chains?.length ? `（${candidate.chains.join(" / ")}）` : ""}</span>
        {targets.filter(([tool]) => tool !== "umapin" || candidate.available_for?.includes("umapin")).map(([tool, label]) => {
          const query = new URLSearchParams({ project, asset_set: dataset, upstream_artifact: candidate.artifact_id! });
          return <a className="btn btn-secondary" key={tool} href={`/analysis/tools/${tool}?${query}`}>{label}</a>;
        })}
      </div>;
    })}
  </section>;
}
