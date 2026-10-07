import {AnalysisResultSummary} from "../results/AnalysisResultSummary";
import {MlResultSummary} from "../results/MlResultSummary";
import { ResultOutputBrowser } from "../results/ResultOutputBrowser";
import { resultComparisons } from "../results/resultOrganization";
import { ViewArea, textOutputKind } from "../results/ResultViewer";
import type { BatchJobSnapshots } from "./useBatchJobSnapshots";
import { BatchResultPanel } from "./BatchResultPanel";
import { ContinueAnalysis } from "../results/ContinueAnalysis";
import { analysisLabel } from "../../shared/utils/analysisLabels";
import { Tabs } from "../../shared/components/Tabs";
import "./JobResultPanel.css";
import { RunManifest } from "../results/RunManifest";
import { useEffect, useMemo, useRef, useState } from "react";
import { useInRouterContext, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { defaultResultFilters, readResultAddress, writeResultAddress, type ResultAddressBinding } from "../results/resultAddress";
import { Download, ExternalLink } from "lucide-react";
import type { JobResultsResponse } from "../../shared/api/jobs";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { kindLabel, type ResultOutput } from "../results";

type Props = {
  result: JobResultsResponse | null;
  loading: boolean;
  embedded?: boolean;
  batchProgress?: BatchJobSnapshots;
  address?: ResultAddressBinding;
};

type ResultSection = "figures" | "tables" | "details";
const resultSections: Array<{key: ResultSection; label: string}> = [
  {key: "figures", label: "图表与报告"}, {key: "tables", label: "数据表"}, {key: "details", label: "分析详情"},
];

type DisplayOutput = ResultOutput & {
  key: string;
  module: string;
  category: string;
  download_url?: string | null;
};

export function JobResultPanel(props: Props) {
  const jobId = String(props.result?.job.job_id || props.result?.job.id || "");
  const routed = useInRouterContext();
  return routed ? <RoutedJobOutputPanel key={jobId} {...props} /> : <JobOutputPanel key={jobId} {...props} />;
}

function RoutedJobOutputPanel(props: Props) {
  const [params]=useSearchParams();
  const navigate=useNavigate();
  const location=useLocation();
  const enabled=location.pathname.endsWith("/script-hub/jobs") && !!params.get("job");
  const address: ResultAddressBinding | undefined=enabled ? {
    value:readResultAddress(params),
    update:value=>navigate({pathname:location.pathname,search:"?"+writeResultAddress(params,value),hash:location.hash},{replace:true}),
  } : undefined;
  return <JobOutputPanel {...props} address={address}/>;
}

function JobOutputPanel({ result, loading, embedded = false, batchProgress, address }: Props) {
  const browserRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const outputs = useMemo(() => normalizeOutputs(result), [result]);
  const viewableOutputs = useMemo(() => outputs.filter((item) => !isArchive(item)), [outputs]);
  const comparisons = useMemo(() => resultComparisons(result?.result), [result?.result]);
  const archiveOutputs = useMemo(() => outputs.filter(isArchive), [outputs]);
  const moduleOptions = useMemo(() => unique(viewableOutputs.map((item) => item.module)), [viewableOutputs]);
  const jobId = String(result?.job.job_id || result?.job.id || "");
  const storageKey = `analysis-result-selection:${jobId}`;
  const addressed = address?.value?.jobId === jobId ? address.value : null;
  const [selection, setSelection] = useState(() => {
    if (addressed) return addressed.selection;
    try {
      const stored = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      return { module: String(stored?.module || ""), output: String(stored?.output || ""), section: String(stored?.section || "") };
    } catch {
      return { module: "", output: "", section: "" };
    }
  });
  const addressSelection = addressed ? JSON.stringify(addressed.selection) : "";
  useEffect(() => {
    if (addressSelection) setSelection(JSON.parse(addressSelection));
  }, [addressSelection]);
  const selectedModule = moduleOptions.includes(selection.module) ? selection.module : moduleOptions[0] || "";
  const moduleOutputs = viewableOutputs.filter(item => item.module === selectedModule);
  const rememberedOutput = moduleOutputs.find(item => item.key === selection.output);
  const availableSections = resultSections.filter(section => section.key === "details" || moduleOutputs.some(item => outputSection(item.kind) === section.key));
  const selectedSection = availableSections.find(section => section.key === selection.section)?.key
    || (rememberedOutput ? outputSection(rememberedOutput.kind) : availableSections[0]?.key) || "details";
  const sectionOutputs = moduleOutputs.filter(item => outputSection(item.kind) === selectedSection);
  const selectedOutput = sectionOutputs.find(item => item.key === selection.output) || sectionOutputs[0] || null;
  const moduleArchives = archiveOutputs.filter(item => !selectedModule || item.module === selectedModule);
  const selectOutput = (module: string, output: string, section?: ResultSection) => {
    const file = viewableOutputs.find(item => item.key === output);
    const next = { module, output, section: section || (file ? outputSection(file.kind) : "details") };
    setSelection(next);
    address?.update({jobId,selection:next,filters:addressed?.selection.module === module ? addressed.filters : {...defaultResultFilters}});
    try { sessionStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Preview remains usable without browser storage. */ }
  };

  if (loading) {
    return <PanelShell embedded={embedded}><EmptyState message="正在读取任务状态与结果…" /></PanelShell>;
  }

  if (!result) {
    return embedded
      ? <PanelShell embedded={embedded}><EmptyState message="暂无可用结果。" /></PanelShell>
      : null;
  }

  if (result.job.module === "analysis-batch") {
    return <PanelShell embedded={embedded}><BatchResultPanel key={result.job.id} result={result} snapshots={batchProgress} selectedJobId={address?.value?.jobId} onSelectJob={id => address?.update({jobId:id,selection:{module:"",output:"",section:""},filters:{...defaultResultFilters}})} renderResult={child => <JobResultPanel result={child} loading={false} embedded />} /></PanelShell>;
  }

  return (
    <PanelShell embedded={embedded}>
      {!embedded && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--spacing-md)",
          }}
        >
          <h4 style={{ margin: 0 }}>{analysisLabel(result.job.module)}</h4>
          <StatusBadge status={result.status} />
        </div>
      )}

      {["failed", "interrupted"].includes(result.status) && (
        <div role="alert" style={{ padding: "var(--spacing-md)", borderRadius: "var(--radius-control)", background: "var(--bg-root)", border: "1px solid var(--danger)" }}>
          <strong>{result.status === "interrupted" ? "分析运行已中断" : "分析未成功完成"}</strong>
          <p style={{ marginBottom: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {String(result.job.detail || result.job.error || "请查看任务记录，核对输入和参数后重新分析。")}
          </p>
        </div>
      )}
      {result.status === "running" && result.job.cancel_requested && <p role="status">正在取消分析，等待计算在检查点停止；停止后可重试或删除任务。</p>}
      {result.status === "cancelled" && <p role="status">分析已取消；已生成的文件仍可查看，未完成部分不作为完整分析结果。</p>}
      <AnalysisResultSummary result={result} />
      <ContinueAnalysis result={result} />
      {result.job.module === "ml-analysis" && result.status === "completed" && <MlResultSummary storageKey={storageKey + ":ml"} metadata={result.result.metadata}
        availableFiles={viewableOutputs.filter(item => item.module === "ml-analysis" && outputSection(item.kind) === "tables").map(outputFileName)}
        onOpenFile={name => {const output = viewableOutputs.find(item => item.module === "ml-analysis" && outputFileName(item) === name); if (output) {selectOutput(output.module, output.key, "tables"); requestAnimationFrame(() => {previewRef.current?.focus({preventScroll: true}); previewRef.current?.scrollIntoView?.({block: "start"});});}}} />}
      {viewableOutputs.length > 0 ? (
        <div style={{ display: "grid", gap: "var(--spacing-md)" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))",
              gap: "var(--spacing-sm)",
              alignItems: "end",
            }}
          >
            <SelectField
              label="分析模块"
              value={selectedModule}
              onChange={module => selectOutput(module, viewableOutputs.find(item => item.module === module && outputSection(item.kind) === selectedSection)?.key || viewableOutputs.find(item => item.module === module)?.key || "")}
              options={moduleOptions.map((value) => ({ value, label: analysisLabel(value) }))}
            />
          </div>
          <div className="job-result-sections">
            <Tabs tabs={availableSections.map(section => ({ key: section.key, label: section.key === "details" ? section.label : `${section.label}（${moduleOutputs.filter(item => outputSection(item.kind) === section.key).length}）` }))}
              activeKey={selectedSection}
              onChange={section => selectOutput(selectedModule, moduleOutputs.find(item => outputSection(item.kind) === section)?.key || "", section as ResultSection)} />
          </div>
          <section role="tabpanel" aria-label={resultSections.find(section => section.key === selectedSection)?.label} className="job-result-content">
          {selectedSection === "details" && <RunManifest results={[result]} />}
          {selectedSection === "figures" && <div ref={browserRef}><ResultOutputBrowser key={selectedModule} outputs={sectionOutputs} selectedKey={selectedOutput?.key || ""} onSelect={output => { selectOutput(selectedModule, output); previewRef.current?.focus({preventScroll: true}); previewRef.current?.scrollIntoView?.({block: "start"}); }} storageKey={storageKey + ":figures:" + selectedModule} comparisons={comparisons}
            addressFilters={addressed?.selection.module === selectedModule ? addressed.filters : undefined}
            onFiltersChange={filters => address?.update({jobId,selection:{module:selectedModule,output:selectedOutput?.key || "",section:"figures"},filters})} /></div>}
          {selectedSection !== "figures" && sectionOutputs.length > 0 && <SelectField
              label="结果文件"
              value={selectedOutput?.key || ""}
              onChange={output => selectOutput(selectedModule, output)}
              options={sectionOutputs.map((item) => ({
                value: item.key,
                label: `${item.category} · ${item.label || kindLabel(item.kind)}`,
              }))}
            />}

          {selectedOutput && <div ref={previewRef} tabIndex={-1} aria-label="当前结果预览" className="job-result-preview">
          {selectedSection === "figures" && <button type="button" className="job-result-back" onClick={() => { const target = browserRef.current?.querySelector<HTMLElement>('button[aria-pressed="true"]') || browserRef.current?.querySelector<HTMLElement>("input"); target?.focus({preventScroll: true}); target?.scrollIntoView?.({block: "center"}); }}>返回图表列表</button>}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "var(--spacing-md)",
                padding: "var(--spacing-md)",
                borderRadius: "var(--radius-control)",
                background: "var(--bg-root)",
                border: "1px solid var(--separator)",
                flexWrap: "wrap",
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: "0.88rem" }}>
                  {selectedOutput.label || kindLabel(selectedOutput.kind)}
                </div>
                <div style={{ color: "var(--text-secondary)", fontSize: "0.76rem", marginTop: "3px" }}>
                  {selectedOutput.category} · {kindLabel(selectedOutput.kind)}
                </div>
              </div>
              <a
                href={["html", "pdf"].includes(selectedOutput.kind) ? selectedOutput.url : selectedOutput.download_url || selectedOutput.url}
                target="_blank"
                rel="noreferrer"
                style={downloadButtonStyle}
              >
                <ExternalLink size={15} />
                {selectedOutput.kind === "html" ? "打开交互报告" : "打开结果文件"}
              </a>
            </div>
          <ViewArea jobId={String(result.job.id || result.job.job_id)} key={selectedOutput.key} kind={selectedOutput.kind} label={selectedOutput.label || undefined} url={selectedOutput.url} downloadUrl={selectedOutput.download_url || undefined} /></div>}
          </section>
        </div>
      ) : (
        <EmptyState message="暂无可预览结果；如有压缩包，可在下方下载。" />
      )}

      {!viewableOutputs.length && <RunManifest results={[result]} />}
      {moduleArchives.length > 0 && (
        <div style={{ display: "grid", gap: "var(--spacing-sm)" }}>
          <div style={sectionLabelStyle}>下载结果压缩包</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
            {moduleArchives.map((item) => (
              <a
                key={item.key}
                href={item.download_url || item.url}
                download
                target="_blank"
                rel="noreferrer"
                style={downloadButtonStyle}
                title={item.label || item.module}
              >
                <Download size={15} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {analysisLabel(item.module)}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}

      {result.assets.length > 0 && (
        <div style={{ display: "grid", gap: "var(--spacing-sm)" }}>
          <div style={sectionLabelStyle}>已登记的结果文件</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
            {result.assets.map((asset) => (
              <a
                key={asset.id}
                href={asset.download_url || asset.preview_url || "#"}
                target="_blank"
                rel="noreferrer"
                style={assetLinkStyle}
                title={asset.original_name}
              >
                <ExternalLink size={14} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {asset.original_name}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}
    </PanelShell>
  );
}

function PanelShell({ children, embedded }: { children: React.ReactNode; embedded?: boolean }) {
  if (embedded) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
        {children}
      </div>
    );
  }

  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        padding: "var(--spacing-xl)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-lg)",
      }}
    >
      {children}
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label style={{ display: "grid", gap: "6px", minWidth: 0 }}>
      <span style={sectionLabelStyle}>{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        style={{
          width: "100%",
          minHeight: "38px",
          border: "1px solid var(--separator)",
          borderRadius: "var(--radius-control)",
          background: "var(--bg-root)",
          color: "var(--text-primary)",
          padding: "0 10px",
          fontSize: "0.86rem",
        }}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div
      style={{
        background: "var(--bg-root)",
        border: "1px solid var(--separator)",
        borderRadius: "var(--radius-control)",
        padding: "var(--spacing-xl)",
        textAlign: "center",
        color: "var(--text-tertiary)",
      }}
    >
      {message}
    </div>
  );
}

function normalizeOutputs(result: JobResultsResponse | null): DisplayOutput[] {
  if (!result) return [];
  const baseModule = result.job.module || "Result";
  const rawOutputs: ResultOutput[] = [...(result.outputs || [])];

  for (const asset of result.assets || []) {
    const url = asset.preview_url || asset.download_url || "";
    if (!url) continue;
    rawOutputs.push({
      label: asset.original_name || "Asset",
      url,
      kind: kindFromAsset(asset),
      module: assetModule(asset, baseModule),
      category: "已登记数据",
      download_url: asset.download_url || url,
      asset_id: asset.id,
    });
  }

  const seen = new Set<string>();
  const normalized: DisplayOutput[] = [];
  rawOutputs.forEach((output) => {
    const url = String(output.url || "").trim();
    const downloadUrl = String(output.download_url || "").trim();
    if (!url && !downloadUrl) return;
    const module = cleanText(output.module) || resultModuleFromLabel(output.label) || baseModule;
    const keySeed = `${module}:${output.kind}:${url || downloadUrl}:${output.asset_id || ""}`;
    if (seen.has(keySeed)) return;
    seen.add(keySeed);
    const recordedKind = String(output.kind || kindFromUrl(url || downloadUrl)).toLowerCase();
    const kind = textOutputKind(recordedKind, url || downloadUrl) || (output.asset_id ? textOutputKind(recordedKind, output.label || "") : null) || recordedKind;
    normalized.push({
      ...output,
      kind,
      url: url || downloadUrl,
      download_url: downloadUrl || (kind === "zip" ? url : undefined),
      module,
      category: cleanText(output.category) || defaultCategory(kind),
      key: keySeed,
    });
  });
  return normalized;
}

function outputFileName(output: DisplayOutput) {
  const label = String(output.label || "");
  if (["model_comparison.csv", "feature_stability.csv", "stable_features.csv"].includes(label)) return label;
  let path = output.url.split("?")[0];
  try { path = new URL(output.url, "http://result.local").pathname; } catch { /* Historical relative filenames remain readable. */ }
  try { path = decodeURIComponent(path); } catch { /* Preserve original path. */ }
  return path.split("/").at(-1) || "";
}

function isArchive(output: DisplayOutput) {
  return output.kind === "zip" || defaultCategory(output.kind) === "压缩包";
}

function outputSection(kind: string): ResultSection {
  if (["html", "png", "jpg", "jpeg", "svg", "image", "pdf"].includes(kind)) return "figures";
  if (["csv", "tsv", "xlsx", "xls"].includes(kind)) return "tables";
  return "details";
}

function defaultCategory(kind: string) {
  if (kind === "zip") return "压缩包";
  if (kind === "html") return "交互报告";
  if (kind === "png" || kind === "image") return "图表";
  return kindLabel(kind);
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function cleanText(value: unknown) {
  return String(value || "").trim();
}

function resultModuleFromLabel(label: unknown) {
  const text = cleanText(label);
  const marker = text.match(/^(.*?)\s+(viewer|bundle|zip|archive)$/i);
  return marker?.[1]?.trim() || "";
}

function kindFromAsset(asset: { mime_type?: string | null; original_name?: string }) {
  const mime = String(asset.mime_type || "").toLowerCase();
  if (mime.includes("zip")) return "zip";
  if (mime.includes("html")) return "html";
  if (mime.includes("image") || mime.includes("png") || mime.includes("jpeg")) return "image";
  if (mime.includes("pdf")) return "pdf";
  if (mime.includes("csv")) return "csv";
  if (mime.includes("json")) return "json";
  return kindFromUrl(asset.original_name || "");
}

function kindFromUrl(url: string) {
  const lower = url.toLowerCase().split("?")[0];
  if (lower.endsWith(".zip")) return "zip";
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "html";
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".svg")) return "image";
  if (lower.endsWith(".pdf")) return "pdf";
  if (lower.endsWith(".csv")) return "csv";
  if (lower.endsWith(".tsv")) return "tsv";
  if (lower.endsWith(".xlsx")) return "xlsx";
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".ppt") || lower.endsWith(".pptx")) return "ppt";
  return "data";
}

function assetModule(asset: { metadata?: unknown }, fallback: string) {
  const metadata = asset.metadata && typeof asset.metadata === "object" ? asset.metadata as Record<string, unknown> : {};
  return cleanText(metadata.analysis_type) || cleanText(metadata.module) || fallback;
}

const sectionLabelStyle: React.CSSProperties = {
  fontSize: "0.76rem",
  color: "var(--text-secondary)",
  fontWeight: 700,
  textTransform: "uppercase",
};

const downloadButtonStyle: React.CSSProperties = {
  minWidth: "150px",
  maxWidth: "240px",
  minHeight: "36px",
  padding: "8px 12px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--accent)",
  background: "var(--accent)",
  color: "#fff",
  fontSize: "0.82rem",
  fontWeight: 650,
  textDecoration: "none",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "8px",
};

const assetLinkStyle: React.CSSProperties = {
  maxWidth: "260px",
  minHeight: "34px",
  padding: "7px 12px",
  borderRadius: "var(--radius-control)",
  background: "var(--bg-root)",
  color: "var(--text-primary)",
  fontSize: "0.82rem",
  textDecoration: "none",
  border: "1px solid var(--separator)",
  display: "inline-flex",
  alignItems: "center",
  gap: "8px",
};
