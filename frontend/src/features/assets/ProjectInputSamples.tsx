import { useEffect, useState, useRef } from "react";
import { Select } from "../../shared/components/Select";
import { projectAssetDetailPath, projectReturnPath } from "./assetSets";
import { validationLabels } from "./assetLabels";
import { useMediaQuery } from "../../shared/hooks/useMediaQuery";
import { SampleEditSheet } from "../samples/SampleEditSheet";
import type { SampleRecord, SampleUpdatePayload } from "../../shared/api/samples";
import { useLocation, useSearchParams } from "react-router-dom";
import { useApi } from "../../shared/hooks/useApi";
import { apiClient } from "../../shared/api/client";
import { Pagination } from "../../shared/components/Pagination";
import type { PaginationInfo } from "../../shared/components/Pagination";
import "./DataManagement.css";

type InputScope = Record<string, { asset_count: number; unresolved_count: number }>;
type Coverage = { input_scopes?: Record<string, InputScope>; samples: { sample_id: string; asset_set: string; needs_version_selection: boolean;
  registration?: {status: "unregistered" | "registered" | "multiple"; count: number};
  coverage: Record<string, { asset_id: string; name: string; status: string }[]> }[];
  unresolved: { asset_id: string; name: string; status: string; asset_set?: string; kind?: string }[]; pagination: PaginationInfo; note: string; };
function missingCoverageLabel(scope: InputScope | undefined, type: string) {
  if (!scope) return "暂无已识别来源";
  const input = scope[type];
  if (!input?.asset_count) return "尚未提供此类输入";
  return input.unresolved_count > 0 ? "已有文件，样本识别待完成" : "已识别输入中未包含该编号";
}
const kinds = [{ type: "pep", title: "克隆序列表" }, { type: "profile", title: "样本指标表" }, { type: "transcriptome", title: "转录组" }, { type: "deconvolution", title: "免疫细胞浸润" }];
export function ProjectInputSamples({ projectId, revision, onChange, onDraftChange }: { projectId: string; revision: number; onChange?: () => void; onDraftChange?: (dirty: boolean) => void }) {
  const [query, setQuery] = useSearchParams();
  const location=useLocation();
  const mobile = useMediaQuery("(max-width: 768px)");
  const registrationRequest = useRef(0);
  const [editSample, setEditSample] = useState<SampleRecord | null>(null);
  const [opening, setOpening] = useState("");
  const [editError, setEditError] = useState("");
  const [searchDraft, setSearchDraft] = useState(query.get("sample_q") || "");
  useEffect(() => setSearchDraft(query.get("sample_q") || ""), [query.get("sample_q")]);
  async function openRegistration(identifier: string, assetSet: string) {
    const request = ++registrationRequest.current;
    setOpening(`${assetSet}:${identifier}`); setEditError("");
    try {
      const result = await apiClient.get<{ sample: SampleRecord | null; project_name: string }>(`/api/projects/${projectId}/samples/registration`, { sample_id: identifier, asset_set: assetSet }, { skipCache: true });
      if (registrationRequest.current !== request) return;
      setEditSample(result.sample || { id: "", project_id: projectId, project_name: result.project_name,
        sample_id: identifier, sample_name: identifier, sequence_id: null, spices: null, institution: null,
        chain_flag: null, is_healthy: null, illness: null, is_pe: null, contain_method: null, iso_tag: null,
        extra_metadata: { asset_set: assetSet }, created_at: null, updated_at: null });
    } catch (reason) { if (registrationRequest.current === request) setEditError(reason instanceof Error ? reason.message : "登记信息读取失败"); }
    finally { if (registrationRequest.current === request) setOpening(""); }
  }
  async function saveRegistration(fields: SampleUpdatePayload) {
    if (!editSample) return;
    await apiClient.post(`/api/projects/${projectId}/samples/registration`, { sample_id: editSample.sample_id,
      asset_set: editSample.extra_metadata.asset_set, fields });
    apiClient.invalidateCache(); onChange ? onChange() : samples.refetch();
  }
  const page = Math.max(1, Math.floor(Number(query.get("sample_page")) || 1));
  const dataset = query.get("asset_set") || "";
  useEffect(()=>{setOpening("");setEditSample(null);setEditError("");return ()=>{registrationRequest.current++;};},[projectId,dataset]);
  const samples = useApi(() => apiClient.get<Coverage>(`/api/projects/${projectId}/input-samples`, { asset_set: dataset, q: query.get("sample_q") || "", state: query.get("sample_state") || "", registration_state: query.get("sample_registration") || "", page, page_size: 50 }), [projectId, dataset, query.get("sample_q"), query.get("sample_state"), query.get("sample_registration"), page, revision]);
  useEffect(() => {
    if (samples.status !== "ready" || samples.data.pagination?.page !== page) return;
    const lastPage = Math.max(1, samples.data.pagination.total_pages);
    if (page > lastPage) setQuery(previous => {
      const next = new URLSearchParams(previous);
      lastPage > 1 ? next.set("sample_page", String(lastPage)) : next.delete("sample_page");
      return next;
    }, { replace: true });
  }, [samples.status, samples.status === "ready" ? samples.data.pagination : null, page, setQuery]);
  const hasSampleFilters = !!query.get("sample_q") || !!query.get("sample_state") || !!query.get("sample_registration");
  const emptyLabel = hasSampleFilters ? "没有符合当前筛选的输入样本，请调整或清除筛选。"
    : samples.status === "ready" && samples.data.unresolved.length > 0 ? "样本识别尚未完成，请先查看文件校验与映射。"
    : "尚未识别样本。请导入任一所需输入，完成校验及映射。";
  const searchPending = searchDraft.trim() !== (query.get("sample_q") || "");
  function clearSampleFilters() {
    setSearchDraft("");
    setQuery(previous => {
      const next = new URLSearchParams(previous);
      for (const key of ["sample_q", "sample_state", "sample_registration", "sample_page"]) next.delete(key);
      return next;
    });
  }
  return <div className="data-section"><div className="data-section-header"><div><h3>输入中识别的样本</h3><p>{dataset ? `当前数据集：${dataset}` : "当前项目全部数据集"}；保留原始编号，不自动合并或剔除样本。</p></div>
    <a className="btn btn-secondary" href={`/management/samples?${new URLSearchParams({project_id:projectId,asset_set:dataset,return_to:projectReturnPath(projectId,location.pathname+location.search+location.hash,`/management/projects/${encodeURIComponent(projectId)}?tab=samples&asset_set=${encodeURIComponent(dataset)}`)})}`}>补充登记信息</a></div>
    <form className="data-query-bar" onSubmit={event => { event.preventDefault(); setQuery(previous => { const next = new URLSearchParams(previous); searchDraft.trim() ? next.set("sample_q", searchDraft.trim()) : next.delete("sample_q"); next.delete("sample_page"); return next; }); }}>
      <input className="input" aria-label="搜索输入样本编号" placeholder="搜索原始样本编号" value={searchDraft} onChange={event => setSearchDraft(event.target.value)} />
      <Select value={query.get("sample_state") || ""} ariaLabel="输入样本状态筛选" options={[{value:"",label:"全部输入样本"}, {value:"needs_attention",label:"识别或校验待处理"}, {value:"multiple",label:"需选择版本"}]}
        onChange={value => setQuery(previous => { const next = new URLSearchParams(previous); value ? next.set("sample_state",value) : next.delete("sample_state"); next.delete("sample_page"); return next; })} />
      <Select value={query.get("sample_registration") || ""} ariaLabel="样本登记状态筛选" options={[{value:"",label:"全部登记状态"},{value:"unregistered",label:"未登记"},{value:"registered",label:"已登记"},{value:"multiple",label:"多条登记待核对"}]}
        onChange={value => setQuery(previous => { const next = new URLSearchParams(previous); value ? next.set("sample_registration",value) : next.delete("sample_registration"); next.delete("sample_page"); return next; })} />
      <button className="btn btn-secondary" type="submit">查询样本</button>
      {(searchDraft || query.get("sample_q") || query.get("sample_state") || query.get("sample_registration")) && <button className="btn btn-secondary" type="button" onClick={clearSampleFilters}>清除样本筛选</button>}
    </form>
    {searchPending && <p className="data-muted" role="status">搜索编号尚未应用；点击“查询样本”更新列表。</p>}
    {editError && <p className="data-error" role="alert">{editError}</p>}
    {editSample && <SampleEditSheet key={`${editSample.id}:${editSample.sample_id}`} sample={editSample} onDraftChange={onDraftChange} open onClose={() => setEditSample(null)} onSave={saveRegistration} />}
    {samples.status === "loading" && <p role="status">正在读取样本覆盖…</p>}
    {samples.status === "error" && <p className="data-error" role="alert">{samples.error}<button className="btn btn-secondary" onClick={samples.refetch}>重新读取</button></p>}
    {samples.status === "ready" && <><p className="data-muted">{samples.data.note} 各类输入按所选分析提供，未提供的可选输入不视为错误。</p>
      {samples.data.unresolved.length > 0 && <details><summary>{samples.data.unresolved.length} 个文件尚未识别样本，查看校验或映射</summary><ul>{samples.data.unresolved.slice(0, 10).map(item => <li key={item.asset_id}><a href={projectAssetDetailPath(projectId, item.asset_id, item.asset_set || dataset, item.kind)}>{item.name}</a> · {validationLabels[item.status] || "尚未校验"}</li>)}</ul>
        {samples.data.unresolved.length > 10 && <p className="data-muted">当前显示前 10 个来源，完整文件清单可在项目数据中查看。</p>}
        <a className="btn btn-secondary" href={`/management/projects/${encodeURIComponent(projectId)}?tab=assets&asset_set=${encodeURIComponent(dataset)}`}>查看全部来源文件</a>
        <a href={`/analysis/center?project=${encodeURIComponent(projectId)}&asset_set=${encodeURIComponent(dataset)}`}>进入分析配置确认列与样本映射</a></details>}
      {mobile ? <div className="data-mobile-records" aria-label="输入样本记录">{samples.data.samples.length ? samples.data.samples.map(sample=><article className="data-mobile-record" key={`${sample.asset_set}:${sample.sample_id}`} aria-label={`输入样本 ${sample.sample_id} · ${sample.asset_set}`}>
        <div className="data-mobile-record-heading"><div><code>{sample.sample_id}</code><p className="data-mobile-record-scope">数据集：{sample.asset_set}</p></div>
          <RegistrationAction projectId={projectId} sample={sample} opening={opening} onOpen={openRegistration}/></div>
        <p className="data-mobile-record-summary">{sample.needs_version_selection?"有多个输入版本，分析前请选择":"按分析配置确认输入"}</p>
        <details className="data-mobile-record-details"><summary>查看输入来源 · {Object.keys(sample.coverage).length} 类</summary>
          <dl>{kinds.map(kind=><div key={kind.type}><dt>{kind.title}</dt><dd><InputSource projectId={projectId} sample={sample} type={kind.type} scope={samples.data.input_scopes?.[sample.asset_set]} expanded/></dd></div>)}</dl>
        </details>
      </article>) : <p className="data-table-empty">{emptyLabel}</p>}</div> : (<div className="data-table-scroll"><table className="data-file-table"><thead><tr><th>数据集</th><th className="data-sample-id">样本编号</th>{kinds.map(kind => <th key={kind.type}>{kind.title}</th>)}<th>版本提示</th><th>登记信息</th></tr></thead>
        <tbody>{samples.data.samples.length ? samples.data.samples.map(sample => <tr key={`${sample.asset_set}:${sample.sample_id}`}><td>{sample.asset_set}</td><td className="data-sample-id"><code>{sample.sample_id}</code></td>
          {kinds.map(kind=><td key={kind.type}><InputSource projectId={projectId} sample={sample} type={kind.type} scope={samples.data.input_scopes?.[sample.asset_set]}/></td>)}
          <td>{sample.needs_version_selection ? "多版本，分析前请选择" : "按分析配置确认"}</td><td><RegistrationAction projectId={projectId} sample={sample} opening={opening} onOpen={openRegistration}/></td></tr>) : <tr><td colSpan={8} className="data-table-empty">{emptyLabel}</td></tr>}</tbody></table></div>)}
      <Pagination pagination={samples.data.pagination} onPageChange={value => setQuery(previous => { const next = new URLSearchParams(previous); next.set("sample_page", String(value)); return next; })} /></>}
  </div>;
}

function RegistrationAction({projectId,sample,opening,onOpen}: {
  projectId:string; sample:Coverage["samples"][number]; opening:string; onOpen:(id:string,dataset:string)=>void;
}) {
  const status=sample.registration?.status;
  const label=status === "registered" ? "已登记" : status === "multiple" ? "多条登记待核对" : "未登记";
  const busy=opening===`${sample.asset_set}:${sample.sample_id}`;
  return <div className="data-registration-action">
    {status && <span className={`data-registration-status is-${status}`}>{label}</span>}
    {status === "multiple" ? <a className="btn btn-secondary" href={`/management/samples?${new URLSearchParams({project_id:projectId,asset_set:sample.asset_set,input_sample_id:sample.sample_id})}`}>核对登记</a>
      : <button className="btn btn-secondary" aria-label={`${status === "registered" ? "查看或编辑" : "补充"}样本 ${sample.sample_id} 的登记信息`}
          disabled={busy} onClick={()=>onOpen(sample.sample_id,sample.asset_set)}>{busy?"正在读取…":status === "registered"?"查看或编辑":"补充信息"}</button>}
  </div>;
}

function InputSource({ projectId, sample, type, scope, expanded = false }: {
  projectId:string; sample:Coverage["samples"][number]; type:string; scope:InputScope|undefined; expanded?:boolean;
}) {
  const sources = sample.coverage[type] || [];
  const fileList = `/management/projects/${projectId}?tab=assets&asset_set=${encodeURIComponent(sample.asset_set)}&file_type=${type}`;
  if (!sources.length) return <span className="data-muted">{missingCoverageLabel(scope,type)}
    {(scope?.[type]?.asset_count || 0)>0 && <a className="data-coverage-action" href={fileList}>查看文件状态</a>}</span>;
  const listing = <><ul>{sources.map(source=><li key={source.asset_id}><a href={projectAssetDetailPath(projectId,source.asset_id,sample.asset_set,type)}>{source.name}</a>
    <span className={`data-validation state-${source.status}`}>{validationLabels[source.status] || "尚未校验"}</span></li>)}</ul><a href={fileList}>查看来源文件</a></>;
  return expanded ? <div className="data-source-detail">{listing}</div> : <details className="data-source-detail">
    <summary>{sources.length} 个来源 · {sources.every(source=>source.status==="valid")?"校验通过":"校验待处理"}</summary>{listing}</details>;
}
