import {apiClient} from "../../shared/api/client";
import {useEffect, useState} from "react";
import type {JobResultsResponse} from "../../shared/api/jobs";
import {listPepCacheCandidates, type PepCacheCandidate} from "../../shared/api/scriptHub";
import {SourceTaskLink} from "../scripthub/modules/SourceSelection";
import "./ContinueAnalysis.css";

function continuationTargets(candidate: PepCacheCandidate): string[][] {
  const targets = candidate.cache_type === "deg" ? [["go-kegg", "GO / KEGG 富集"]]
    : candidate.cache_type === "vj_usage" ? [["vj-difference", "V/J 使用差异"], ["umapin", "UMAP 特征降维"], ["ml", "机器学习"]]
    : candidate.cache_type === "umapin_table" ? [["umapin", "UMAP 特征降维"], ["ml", "机器学习"]]
    : candidate.cache_type === "tra_shared" ? [["mait-nkt", "MAIT / NKT 特征"]] : [];
  return targets.filter(([tool]) => {
    if (tool === "umapin") return candidate.available_for?.includes("umapin");
    if (tool === "vj-difference") return candidate.available_for?.includes("volcano");
    return true;
  });
}
type SourceState = {scope: string; loading: boolean; candidates: PepCacheCandidate[]; unavailable: PepCacheCandidate[]; error: string};

export function ContinueAnalysis({result}: {result: JobResultsResponse}) {
  const job = result.job as unknown as Record<string, unknown>;
  const payload = (job.payload || {}) as Record<string, unknown>;
  const project = String(job.project_id || "");
  const dataset = String(payload.asset_set || "");
  const task = String(job.job_id || job.id || "");
  const differential = [job.module, job.job_type].includes("volcano");
  const enabled = result.status === "completed" && ([job.module, job.job_type].includes("pep-analysis") || differential)
    && !!project && !!dataset && !!task;
  const scope = JSON.stringify([enabled, differential, project, dataset, task]);
  const [state, setState] = useState<SourceState>({scope: "", loading: false, candidates: [], unavailable: [], error: ""});
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let disposed = false;
    setState({scope, loading: enabled, candidates: [], unavailable: [], error: ""});
    if (!enabled) return;
    async function readSources() {
      try {
        let candidates: PepCacheCandidate[];
        if (differential) {
          const response = await apiClient.get<{candidates: Array<{id: string; job_id: string; status: string; reason?: string}>}>(
            "/api/script-hub/go-kegg-enrichment/sources", {project_id: project, asset_set: dataset},
            revision ? {skipCache: true, deduplicate: false} : {skipCache: true});
          candidates = response.candidates.filter(item => item.job_id === task)
            .map(item => ({...item, artifact_id: item.id, cache_type: "deg", label: "本次差异表达结果", path: ""}));
        } else {
          const response = revision
            ? await listPepCacheCandidates(project, undefined, dataset, {deduplicate: false})
            : await listPepCacheCandidates(project, undefined, dataset);
          candidates = response.candidates.filter(item => item.job_id === task);
        }
        if (!disposed) setState({scope, loading: false,
          candidates: candidates.filter(candidate => candidate.status === "available" && candidate.artifact_id && continuationTargets(candidate).length > 0), unavailable: candidates.filter(candidate => candidate.status !== "available" || !candidate.artifact_id || !continuationTargets(candidate).length), error: ""});
      } catch (reason) {
        if (!disposed) setState({scope, loading: false, candidates: [], unavailable: [],
          error: reason instanceof Error ? reason.message : "无法读取后续分析入口"});
      }
    }
    void readSources();
    return () => {disposed = true;};
  }, [enabled, differential, project, dataset, task, scope, revision]);
  if (!enabled) return null;
  const visible = state.scope === scope ? state : {scope, loading: true, candidates: [], unavailable: [], error: ""};
  const context = new URLSearchParams({project, asset_set: dataset});
  return <section className="continue-analysis" aria-label="继续分析" aria-busy={visible.loading}>
    <div className="continue-analysis__header">
      <div><h3>使用本次结果继续分析</h3><p>保留当前项目和数据集，进入配置后确认参数再运行。</p></div>
      <button type="button" className="btn btn-secondary" disabled={visible.loading}
        onClick={() => setRevision(value => value + 1)}>刷新可用结果</button>
    </div>
    {visible.loading && <p role="status" className="continue-analysis__message">正在读取本次分析的后续入口…</p>}
    {visible.error && <div role="alert" className="continue-analysis__message">
      <p>后续分析入口暂时读取失败，请重新读取。</p>
      <button type="button" className="btn btn-secondary" onClick={() => setRevision(value => value + 1)}>重新读取</button>
      <details><summary>查看错误详情</summary><p>{visible.error}</p></details>
    </div>}
    {!visible.loading && !visible.error && !visible.candidates.length && <div className="continue-analysis__message">
      <p>本次结果暂无可直接继续的分析入口。</p><p>{visible.unavailable.length ? "本次产物需要核对条件，具体原因见下方。" : "本任务尚未登记可复用的前置产物。可查看分析详情与结果文件，再选择适合的分析。"}</p>
      <a className="continue-analysis__center" href={"/analysis/center?" + context}>前往分析中心</a>
    </div>}
    {!visible.loading && !visible.error && visible.unavailable.length > 0 && <details className="continue-analysis__message">
      <summary>需核对的本次产物（{visible.unavailable.length}）</summary>
      <ul>{visible.unavailable.map((candidate,index) => <li key={candidate.artifact_id || candidate.id || index}>
        <strong>{candidate.label || "本次前置结果"}</strong><p>{candidate.reason || (candidate.status !== "available" ? "产物当前不可用，请检查来源任务与结果文件。" : !candidate.artifact_id ? "未登记稳定的产物标识，无法直接引用。" : "此类产物暂无兼容的后续分析入口，可下载或查看本次结果。")}</p>
      </li>)}</ul>
      <SourceTaskLink jobId={task} projectId={project} assetSet={dataset}/>
    </details>}
    {!visible.loading && visible.candidates.map(candidate => <article className="continue-analysis__card"
      key={candidate.artifact_id} aria-label={candidate.label || "本次前置结果"}>
      <div className="continue-analysis__source">
        <strong>{candidate.label || "本次前置结果"}</strong>
        <div className="continue-analysis__conditions">
          {candidate.chains?.length ? <span>受体链：{candidate.chains.join(" / ")}</span> : null}
          {(candidate.group_fields?.length || candidate.group_field) ? <span>分组字段：{candidate.group_fields?.length
            ? candidate.group_fields.join("、") : candidate.group_field}</span> : null}
          {typeof candidate.sample_count === "number" && Number.isFinite(candidate.sample_count) && candidate.sample_count > 0
            ? <span>样本：{candidate.sample_count}</span> : null}
        </div>
        <SourceTaskLink jobId={task} projectId={project} assetSet={dataset}/>
      </div>
      <div className="continue-analysis__targets">
        {continuationTargets(candidate).map(([tool, label]) => {
          const query = new URLSearchParams({project, asset_set: dataset, upstream_artifact: candidate.artifact_id!});
          return <a className="btn btn-secondary" key={tool} href={"/analysis/tools/" + tool + "?" + query}>{label}</a>;
        })}
      </div>
    </article>)}
  </section>;
}
