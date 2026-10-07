import { useState, useCallback, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { Pagination } from "../../shared/components/Pagination";
import { apiClient } from "../../shared/api/client";
import { Download, Pencil } from "lucide-react";
import { useApi } from "../../shared/hooks/useApi";
import {
  listSamples,
  updateSample,
  getSampleFieldOptions,
} from "../../shared/api/samples";
import type { SampleRecord, SampleUpdatePayload, ListSamplesParams } from "../../shared/api/samples";
import { UnsavedChangesGuard } from "../../shared/components/UnsavedChangesGuard";
import { PageHeader } from "../../shared/components/PageHeader";
import { Skeleton, SkeletonRow } from "../../shared/components/Skeleton";
import { DataReadError } from "../../features/assets/DataReadError";
import { SampleBatchSheet } from "../../features/samples/SampleBatchSheet";
import { SampleExportSheet, type SampleExportScope } from "../../features/samples/SampleExportSheet";
import { SampleEditSheet } from "../../features/samples/SampleEditSheet";
import { SampleFilters } from "../../features/samples/SampleFilters";
import { SampleRegistryCards } from "../../features/samples/SampleRegistryCards";
import { useMediaQuery } from "../../shared/hooks/useMediaQuery";

import { getProject } from "../../shared/api/projects";
import { projectReturnPath } from "../../features/assets/assetSets";
import { speciesLabel, healthyLabel, pairedLabel, registrationSource, manuallyMaintainedFields, sampleFieldLabels } from "../../features/samples/sampleDisplay";
import "../../features/assets/DataManagement.css";
const PAGE_SIZE = 50;

export function SampleRegistry() {
  const [query, setQuery] = useSearchParams();
  const mobile = useMediaQuery("(max-width: 768px)");
  const allColumns=query.get("sample_columns")==="all";
  const filterKeys = ["project_id", "asset_set", "input_sample_id", "sample_id", "sample_name", "project_name", "institution", "sequence_id", "contain_method", "iso_tag", "spices", "chain_flag", "is_healthy", "illness", "is_pe"] as const;
  const filterSignature=JSON.stringify(filterKeys.map(key=>query.get(key)));
  const filters = useMemo<ListSamplesParams>(() => Object.fromEntries(filterKeys.filter(key => query.get(key)).map(key => [key, query.get(key)!])), [filterSignature]);
  const page = Math.max(1, Math.floor(Number(query.get("page")) || 1));
  const setPage = (value: number) => setQuery(previous => { const next = new URLSearchParams(previous); next.set("page", String(value)); return next; });
  const debouncedSearch = query.get("q") || "";
  const [exportScope,setExportScope]=useState<SampleExportScope|null>(null);
  const [sampleDraft, setSampleDraft] = useState(false);
  const [bulkDraft, setBulkDraft] = useState(false);
  const [selectedRecords, setSelectedRecords] = useState<Map<string, SampleRecord>>(new Map());
  const [bulkContext, setBulkContext] = useState<{projectId:string;assetSet:string;records:SampleRecord[]} | null>(null);
  const selectionScope = JSON.stringify([filters, debouncedSearch]);
  useEffect(() => setSelectedRecords(new Map()), [selectionScope]);
  const selectedRows = [...selectedRecords.values()];
  const oneScope = new Set(selectedRows.map(row => JSON.stringify([row.project_id, row.extra_metadata.asset_set]))).size === 1;
  const selectionReady = oneScope && selectedRows.every(row => !!row.sample_id && !!row.extra_metadata.asset_set);
  function toggleSample(sample: SampleRecord) {
    setSelectedRecords(previous => { const next = new Map(previous); next.has(sample.id) ? next.delete(sample.id) : next.set(sample.id, sample); return next; });
  }
  function togglePage() {
    setSelectedRecords(previous => {
      const next = new Map(previous); const all = sampleList.length > 0 && sampleList.every(row => next.has(row.id));
      for (const row of sampleList) all ? next.delete(row.id) : next.set(row.id, row);
      return next;
    });
  }
  const [editSample, setEditSample] = useState<SampleRecord | null>(null);
  const [searchText, setSearchText] = useState(debouncedSearch);

  useEffect(() => setSearchText(debouncedSearch), [debouncedSearch]);
  useEffect(() => {
    if (searchText === debouncedSearch) return;
    const timer = setTimeout(() => setQuery(previous => { const next = new URLSearchParams(previous); searchText ? next.set("q", searchText) : next.delete("q"); next.delete("page"); return next; }, { replace: true }), 300);
    return () => clearTimeout(timer);
  }, [searchText, debouncedSearch, setQuery]);
  const samples = useApi(() => listSamples({ ...filters, q: debouncedSearch, page, page_size: PAGE_SIZE }), [filters, debouncedSearch, page]);
  useEffect(() => {
    if (samples.status !== "ready" || !samples.data.pagination || samples.data.pagination.page !== page) return;
    const lastPage = Math.max(1, samples.data.pagination.total_pages);
    if (page > lastPage) setQuery(previous => {
      const next = new URLSearchParams(previous);
      lastPage > 1 ? next.set("page", String(lastPage)) : next.delete("page");
      return next;
    }, { replace: true });
  }, [samples.status, samples.status === "ready" ? samples.data.pagination : null, page, setQuery]);
  const options = useApi(() => getSampleFieldOptions(filters.project_id || "", "", filters.asset_set || "", {view:"filters"}), [filters.project_id, filters.asset_set]);
  const scope = useApi(() => getProject(filters.project_id!, { summaryOnly: true }), [filters.project_id], !!filters.project_id);
  const fieldOptions = options.status === "ready" ? options.data.fields : {};

  const sampleList = samples.status === "ready" ? samples.data.samples : [];
  const loading = samples.status === "loading" || samples.status === "idle";
  const error = samples.status === "error" ? samples.error : null;

  const filteredSamples = sampleList;

  const handleFilterChange = (key: keyof ListSamplesParams, value: string) => {
    setQuery(previous => { const next = new URLSearchParams(previous); value ? next.set(key, value) : next.delete(key); next.delete("page"); return next; });
  };

  const handleClearFilters = () => {
    setQuery(previous => { const next = new URLSearchParams(); for (const key of ["project_id", "asset_set", "return_to", "sample_columns"]) { const value = previous.get(key); if (value) next.set(key,value); } return next; });
    setSearchText("");
  };

  const handleExport = () => {
    if(samples.status !== "ready") return;
    setExportScope({filters:{...filters,q:debouncedSearch}, count:samples.data.pagination?.total ?? samples.data.samples.length,
      projectName:filters.project_id ? scope.status === "ready" ? scope.data.name : sampleList[0]?.project_name || "当前项目" : "全部可访问项目"});
  };

  const handleSaveSample = useCallback(
    async (data: SampleUpdatePayload) => {
      if (!editSample) return;
      await updateSample(editSample.id, data);
      apiClient.invalidateCache();
      samples.refetch();
      options.refetch();
    },
    [editSample, samples, options]
  );

  const hasActiveFilters =
    !!filters.input_sample_id ||
    !!filters.project_name ||
    !!filters.sample_id ||
    !!filters.sample_name ||
    !!filters.chain_flag ||
    !!filters.is_healthy ||
    !!filters.spices ||
    !!filters.is_pe;

  return (
    <>
      <UnsavedChangesGuard when={sampleDraft || bulkDraft} />
      <PageHeader title="样本登记" subtitle={samples.status === "ready" ? `补充登记信息 · ${samples.data.pagination?.total ?? filteredSamples.length} 个样本` : samples.status === "error" ? "补充登记信息 · 样本数量暂未读取" : "补充登记信息 · 正在读取样本…"}>
        <button className="btn btn-primary" onClick={() => setBulkContext({projectId:filters.project_id || "",assetSet:filters.asset_set || "",records:[]})}>批量登记</button>
        <button className="btn btn-secondary" onClick={handleExport} disabled={samples.status !== "ready"} title="导出当前已应用筛选的全部登记信息"><Download size={16}/>导出数据表</button>
      </PageHeader>

      {exportScope && <SampleExportSheet scope={exportScope} onClose={()=>setExportScope(null)}/> }

      {mobile ? <details className="data-registry-help"><summary>登记说明</summary><p>这里编辑补充登记信息，不会修改原始输入文件。输入中识别的样本与跨数据覆盖请在项目的“样本”标签查看。</p></details> : <p style={{ color: "var(--text-secondary)", lineHeight: 1.6 }}>这里编辑补充登记信息，不会修改原始输入文件。输入中识别的样本与跨数据覆盖请在项目的“样本”标签查看。</p>}
      {filters.project_id && <div className="data-scope-bar"><span>当前项目：{scope.status === "ready" ? scope.data.name : sampleList[0]?.project_name || (scope.status === "error" ? "项目名称暂时无法读取" : "正在读取项目名称…")}{filters.asset_set ? ` · 数据集：${filters.asset_set}` : " · 全部数据集"}</span><a className="btn btn-secondary" href={projectReturnPath(filters.project_id,query.get("return_to") || "",`/management/projects/${encodeURIComponent(filters.project_id)}?tab=samples&asset_set=${encodeURIComponent(filters.asset_set || "")}`)}>返回项目样本</a></div>}
      {filters.input_sample_id && <div className="data-scope-bar" role="status"><span>当前核对输入编号：<code>{filters.input_sample_id}</code>；仅显示关联到此编号的登记，不自动合并。</span>
        <button className="btn btn-secondary" onClick={() => setQuery(previous => {const next = new URLSearchParams(previous);next.delete("input_sample_id");next.delete("page");return next;})}>查看数据集全部登记</button></div>}
      {selectedRows.length > 0 && <div className="sample-batch-selection" role="region" aria-label="所选登记操作"><strong>已选择 {selectedRows.length} 条登记</strong>
        <button className="btn btn-primary" disabled={!selectionReady} onClick={() => setBulkContext({projectId:selectedRows[0].project_id,assetSet:String(selectedRows[0].extra_metadata.asset_set),records:selectedRows})}>批量修改所选</button>
        <button className="btn btn-secondary" disabled={selectedRows.length>5000 || samples.status!=="ready"} onClick={()=>setExportScope({
          filters:{...filters,q:debouncedSearch}, count:selectedRows.length, recordIds:selectedRows.map(row=>row.id),
          projectName:filters.project_id ? scope.status === "ready" ? scope.data.name : "当前项目" : "所选可访问项目"})}><Download size={16}/>导出所选</button>
        <button className="btn btn-secondary" onClick={() => setSelectedRecords(new Map())}>清除所选登记</button>
        {selectedRows.length > 5000 && <span role="status">单次所选导出最多 5000 条，请减少选择。若要导出当前筛选的全部匹配记录，请使用页面上方“导出数据表”，并核对导出范围。</span>}
        {!selectionReady && <span>请先限定同一项目和数据集；未标记来源的旧登记请逐条核对。</span>}</div>}
      {bulkContext && <SampleBatchSheet initialProjectId={bulkContext.projectId} initialAssetSet={bulkContext.assetSet} selectedRecords={bulkContext.records}
        onClose={() => setBulkContext(null)} onDraftChange={setBulkDraft} onSaved={() => {apiClient.invalidateCache();samples.refetch();options.refetch();setSelectedRecords(new Map());}} />}
      {options.status === "error" && <DataReadError title="筛选候选暂时无法读取" message={options.error} onRetry={options.refetch} retryLabel="重新读取筛选候选" />}
      {/* Filter toolbar */}
      <SampleFilters
        onApplyFilters={draft => setQuery(previous => {
          const next = new URLSearchParams(previous);
          for (const key of filterKeys) {
            if (key === "project_id" || key === "asset_set" || key === "input_sample_id") continue;
            const value = draft[key]; value ? next.set(key, String(value)) : next.delete(key);
          }
          next.delete("page"); return next;
        })}
        fieldOptions={fieldOptions}
        filters={filters}
        searchText={searchText}
        onFilterChange={handleFilterChange}
        onSearchChange={setSearchText}
        onClear={handleClearFilters}
        hasActiveFilters={hasActiveFilters || !!searchText}
      />

      {!mobile && <div className="sample-column-toolbar"><div><strong>登记列表</strong><span>常用信息优先，其他字段可在编辑中查看</span></div><div className="sample-column-switch" role="group" aria-label="登记表显示字段">
        <button aria-pressed={!allColumns} onClick={()=>setQuery(previous=>{const next=new URLSearchParams(previous);next.delete("sample_columns");return next;})}>常用列</button>
        <button aria-pressed={allColumns} onClick={()=>setQuery(previous=>{const next=new URLSearchParams(previous);next.set("sample_columns","all");return next;})}>全部字段</button>
      </div></div>}
      {/* Sample table */}
      <SampleTable
        allColumns={allColumns}
        samples={filteredSamples}
        loading={loading}
        error={error}
        onRetry={samples.refetch}
        onEdit={setEditSample}
        selectedIds={new Set(selectedRecords.keys())} onToggle={toggleSample} onTogglePage={togglePage}
      />

      {samples.status === "ready" && samples.data.pagination && <Pagination pagination={samples.data.pagination} onPageChange={setPage} />}
      {/* Edit sample sheet */}
      {editSample && (
        <SampleEditSheet
          key={editSample.id}
          sample={editSample}
          onDraftChange={setSampleDraft}
          open
          onClose={() => setEditSample(null)}
          onSave={handleSaveSample}
        />
      )}
    </>
  );
}

/* ── Filter Toolbar ─────────────────────────────────────────────────── */

/* ── Sample Table ───────────────────────────────────────────────────── */

const SAMPLE_COLUMNS = [
  "样本编号",
  "名称",
  "项目",
  "数据集",
  "链类型",
  "健康状态",
  "物种",
  "疾病",
  "序列编号",
  "双端测序",
  "所属机构",
  "纳入方法",
  "同型标签",
  "操作",
] as const;

function SampleTable({
  samples,
  loading,
  error,
  onEdit,
  onRetry,
  allColumns,
  selectedIds, onToggle, onTogglePage,
}: {
  samples: SampleRecord[];
  allColumns: boolean;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onEdit: (sample: SampleRecord) => void;
  selectedIds: Set<string>; onToggle: (sample: SampleRecord) => void; onTogglePage: () => void;
}) {
  const mobile = useMediaQuery("(max-width: 768px)");
  if (error) {
    return <DataReadError title="样本加载失败" message={error} onRetry={onRetry} retryLabel="重新读取样本" />;
  }

  if (mobile) return <>
    {!loading && samples.length > 0 && <div className="sample-batch-page-selection"><label className="sample-batch-select"><input type="checkbox" aria-label="选择当前页全部登记" checked={samples.every(sample => selectedIds.has(sample.id))} onChange={onTogglePage}/>选择本页 {samples.length} 条</label></div>}
    <SampleRegistryCards samples={samples} loading={loading} onEdit={onEdit} selectedIds={selectedIds} onToggle={onToggle}/>
  </>;

  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        overflow: "auto",
      }}
    >
      <table className={`data-sample-registry-table${allColumns ? "" : " sample-common-columns"}`} style={{ width: "100%", borderCollapse: "collapse", minWidth: allColumns ? "1400px" : "800px" }}>
        <thead>
          <tr style={{ background: "var(--bg-root)", borderBottom: "1px solid var(--separator)" }}>
            <th scope="col" style={{padding:"12px",width:"44px"}}><input type="checkbox" aria-label="选择当前页全部登记" disabled={loading || !samples.length} checked={!!samples.length && samples.every(sample => selectedIds.has(sample.id))} onChange={onTogglePage}/></th>
            {SAMPLE_COLUMNS.map((h) => (
              <th
                key={h}
                scope="col"
                className={h === "样本编号" ? "data-sample-id" : undefined}
                style={{
                  textAlign: "left",
                  padding: "12px 14px",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  color: "var(--text-secondary)",
                  whiteSpace: "nowrap",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <SkeletonRow columns={SAMPLE_COLUMNS.length + 1} />
          ) : samples.length === 0 ? (
            <tr>
              <td
                colSpan={SAMPLE_COLUMNS.length + 1}
                style={{
                  padding: "var(--spacing-3xl) var(--spacing-lg)",
                  textAlign: "center",
                  color: "var(--text-tertiary)",
                }}
              >
                未找到样本，请调整筛选条件。
              </td>
            </tr>
          ) : (
            samples.map((sample) => (
              <tr
                key={sample.id}
                style={{
                  borderBottom: "1px solid var(--separator)",
                  transition: "background var(--duration-fast)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--bg-inset)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "";
                }}
              >
                <td style={{padding:"12px"}}><input type="checkbox" aria-label={`选择登记 ${sample.sample_id || sample.sample_name}（${String(sample.extra_metadata.asset_set || "未标记来源")}）`} checked={selectedIds.has(sample.id)} onChange={() => onToggle(sample)}/></td>
                <td className="data-sample-id" style={cellStyle}>
                  <code style={{ fontSize: "0.8rem", background: "var(--bg-inset)", padding: "2px 6px", borderRadius: "4px" }}>
                    {sample.sample_id || "—"}
                  </code>
                </td>
                <td style={{ ...cellStyle, maxWidth: "160px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {sample.sample_name}
                  <small className="data-registration-source">{registrationSource(sample.extra_metadata)}</small>
                  {manuallyMaintainedFields(sample.extra_metadata).length > 0 && <details className="data-registration-fields">
                    <summary>人工维护 {manuallyMaintainedFields(sample.extra_metadata).length} 项</summary>
                    <span>{manuallyMaintainedFields(sample.extra_metadata).map(field=>sampleFieldLabels[field] || "其他补充字段").join("、")}</span>
                  </details>}
                </td>
                <td style={cellStyle}>
                  {sample.project_name || "—"}
                </td>
                <td style={cellStyle}>{String(sample.extra_metadata?.asset_set || "未标记来源")}</td>
                <td style={cellStyle}>
                  <span style={chipStyle}>{sample.chain_flag || "—"}</span>
                </td>
                <td style={cellStyle}>
                  <span
                    style={{
                      ...chipStyle,
                      background: sample.is_healthy === "yes" ? "rgba(52,199,89,0.12)" : sample.is_healthy === "no" ? "rgba(255,59,48,0.12)" : "var(--bg-inset)",
                      color: sample.is_healthy === "yes" ? "var(--success)" : sample.is_healthy === "no" ? "var(--danger)" : "var(--text-secondary)",
                    }}
                  >
                    {healthyLabel(sample.is_healthy)}
                  </span>
                </td>
                <td style={cellStyle}>{speciesLabel(sample.spices)}</td>
                <td style={{ ...cellStyle, maxWidth: "120px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {sample.illness || "—"}
                </td>
                <td style={cellStyle}>
                  <code style={{ fontSize: "0.8rem", background: "var(--bg-inset)", padding: "2px 6px", borderRadius: "4px" }}>
                    {sample.sequence_id || "—"}
                  </code>
                </td>
                <td style={cellStyle}>
                  <span style={chipStyle}>{pairedLabel(sample.is_pe)}</span>
                </td>
                <td style={{ ...cellStyle, maxWidth: "140px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {sample.institution || "—"}
                </td>
                <td style={cellStyle}>{sample.contain_method || "—"}</td>
                <td style={cellStyle}>{sample.iso_tag || "—"}</td>
                <td style={cellStyle}>
                  <button className="btn btn-secondary sample-edit-button" onClick={() => onEdit(sample)}>
                    <Pencil size={14} />
                    编辑
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

/* ── Sample Edit Sheet ──────────────────────────────────────────────── */

/* ── Styles ─────────────────────────────────────────────────────────── */

const cellStyle: React.CSSProperties = {
  padding: "10px 14px",
  fontSize: "0.85rem",
  color: "var(--text-primary)",
};

const chipStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 8px",
  borderRadius: "var(--radius-pill)",
  background: "var(--bg-inset)",
  fontSize: "0.75rem",
  color: "var(--text-secondary)",
};
