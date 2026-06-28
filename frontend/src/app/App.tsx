import { Activity, Boxes, Database, FlaskConical, GitBranch, ListChecks, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { listJobs } from "../shared/api/jobs";
import {
  getProject,
  listProjectAssets,
  listProjects,
  projectAssetDownloadUrl,
  projectAssetPreviewUrl,
  type Pagination,
  uploadProjectAssets
} from "../shared/api/projects";
import type { JobSummary, ProjectAsset, ProjectSummary } from "../shared/types/domain";

type LoadState = "idle" | "loading" | "ready" | "error";
type DetailTab = "assets" | "results" | "jobs";

const assetPageSize = 8;
const uploadAssetTypes = ["profile", "pep", "transcriptome", "sample_summary", "group_spec", "ppt_template", "pdf_source", "raw_archive"];

export function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedProject, setSelectedProject] = useState<ProjectSummary | null>(null);
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [results, setResults] = useState<ProjectAsset[]>([]);
  const [assetPagination, setAssetPagination] = useState<Pagination | undefined>();
  const [assetPage, setAssetPage] = useState(1);
  const [detailTab, setDetailTab] = useState<DetailTab>("assets");
  const [detailRefreshKey, setDetailRefreshKey] = useState(0);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [detailState, setDetailState] = useState<LoadState>("idle");
  const [uploadAssetType, setUploadAssetType] = useState("profile");
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [uploadState, setUploadState] = useState<LoadState>("idle");
  const [uploadMessage, setUploadMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoadState("loading");
    Promise.all([listProjects(), listJobs({ limit: 8 })])
      .then(([projectPayload, jobPayload]) => {
        if (cancelled) return;
        const nextProjects = projectPayload.projects || [];
        setProjects(nextProjects);
        setJobs(jobPayload.jobs || []);
        setSelectedProjectId(nextProjects[0]?.id || "");
        setLoadState("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Unable to load API data");
        setLoadState("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setSelectedProject(null);
      setAssets([]);
      setResults([]);
      setAssetPagination(undefined);
      return;
    }
    let cancelled = false;
    setDetailState("loading");
    Promise.all([
      getProject(selectedProjectId),
      listProjectAssets(selectedProjectId, { page: assetPage, pageSize: assetPageSize }),
      listProjectAssets(selectedProjectId, { assetType: "processed_result", page: 1, pageSize: 8 }),
      listJobs({ projectId: selectedProjectId, limit: 8 })
    ])
      .then(([projectPayload, assetPayload, resultPayload, jobPayload]) => {
        if (cancelled) return;
        setSelectedProject(projectPayload);
        setAssets(assetPayload.assets || []);
        setResults(resultPayload.assets || []);
        setAssetPagination(assetPayload.pagination);
        setJobs(jobPayload.jobs || []);
        setDetailState("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setDetailState("error");
        setError(err instanceof Error ? err.message : "Unable to load project detail");
      });
    return () => {
      cancelled = true;
    };
  }, [assetPage, detailRefreshKey, selectedProjectId]);

  const stats = useMemo(() => {
    const resultCount = projects.reduce((sum, project) => sum + Number(project.result_count || 0), 0);
    const sampleCount = projects.reduce((sum, project) => sum + Number(project.sample_count || 0), 0);
    const runningJobs = jobs.filter((job) => job.status === "running" || job.status === "queued").length;
    return {
      projects: projects.length,
      resultCount,
      sampleCount,
      runningJobs
    };
  }, [projects, jobs]);

  const selectedJobs = selectedProjectId ? jobs.filter((job) => !job.project_id || job.project_id === selectedProjectId) : jobs;

  const handleUpload = async () => {
    if (!selectedProjectId || uploadFiles.length === 0) return;
    setUploadState("loading");
    setUploadMessage("");
    try {
      const payload = await uploadProjectAssets(selectedProjectId, {
        assetType: uploadAssetType,
        files: uploadFiles,
        replaceExisting
      });
      setUploadState("ready");
      setUploadMessage(`${payload.assets.length} asset${payload.assets.length === 1 ? "" : "s"} uploaded.`);
      setUploadFiles([]);
      setAssetPage(1);
      setDetailRefreshKey((key) => key + 1);
    } catch (err) {
      setUploadState("error");
      setUploadMessage(err instanceof Error ? err.message : "Upload failed");
    }
  };

  return (
    <main className="shell">
      <aside className="rail" aria-label="Primary navigation">
        <div className="brand-mark">IR</div>
        <button className="rail-button is-active" aria-label="Projects">
          <Boxes size={20} />
        </button>
        <button className="rail-button" aria-label="Jobs">
          <Activity size={20} />
        </button>
        <button className="rail-button" aria-label="Data">
          <Database size={20} />
        </button>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Migration console</p>
            <h1>Immune Repertoire Platform</h1>
          </div>
          <div className="status-pill">
            <GitBranch size={16} />
            Flask API bridge
          </div>
        </header>

        <section className="hero-band">
          <div>
            <p className="eyebrow">Phase 1</p>
            <h2>Project and asset workspace now backed by stable API contracts</h2>
          </div>
          <div className="hero-grid" aria-label="Platform summary">
            <Metric label="Projects" value={stats.projects} />
            <Metric label="Samples" value={stats.sampleCount} />
            <Metric label="Results" value={stats.resultCount} />
            <Metric label="Active jobs" value={stats.runningJobs} />
          </div>
        </section>

        {loadState === "error" && <div className="notice">{error}</div>}

        <section className="split">
          <div className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Projects</p>
                <h3>Recent workspace inventory</h3>
              </div>
              <FlaskConical size={20} />
            </div>
            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Assets</th>
                    <th>Results</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.slice(0, 10).map((project) => (
                    <tr
                      className={project.id === selectedProjectId ? "is-selected" : ""}
                      key={project.id}
                      onClick={() => {
                        setSelectedProjectId(project.id);
                        setAssetPage(1);
                      }}
                    >
                      <td>{project.name}</td>
                      <td>{project.status}</td>
                      <td>{Object.values(project.asset_counts || {}).reduce((sum, count) => sum + count, 0)}</td>
                      <td>{project.result_count || 0}</td>
                    </tr>
                  ))}
                  {loadState === "loading" && <PlaceholderRows columns={4} rows={4} />}
                  {loadState === "ready" && projects.length === 0 && (
                    <tr>
                      <td colSpan={4}>No projects returned by the API.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Jobs</p>
                <h3>Unified task stream</h3>
              </div>
              <ListChecks size={20} />
            </div>
            <JobList jobs={selectedJobs} emptyLabel="No jobs returned for the selected project." loading={loadState === "loading"} />
          </div>
        </section>

        <section className="detail-panel">
          <div className="detail-header">
            <div>
              <p className="eyebrow">Project detail</p>
              <h3>{selectedProject?.name || "Select a project"}</h3>
              {selectedProject && (
                <p className="subtle">
                  {selectedProject.institution || "No institution"} · {selectedProject.sample_count || 0} samples · {selectedProject.result_count || 0} results
                </p>
              )}
            </div>
            <button
              aria-label="Refresh selected project"
              className="icon-action"
              disabled={!selectedProjectId}
              onClick={() => setDetailRefreshKey((key) => key + 1)}
              type="button"
            >
              <RefreshCw size={18} />
            </button>
          </div>

          <div className="tabs" role="tablist" aria-label="Project detail tabs">
            <button className={detailTab === "assets" ? "is-active" : ""} onClick={() => setDetailTab("assets")} type="button">
              Assets
            </button>
            <button className={detailTab === "results" ? "is-active" : ""} onClick={() => setDetailTab("results")} type="button">
              Results
            </button>
            <button className={detailTab === "jobs" ? "is-active" : ""} onClick={() => setDetailTab("jobs")} type="button">
              Jobs
            </button>
          </div>

          {detailState === "error" && <div className="notice">{error}</div>}
          {detailTab === "assets" && (
            <>
              <AssetUploadForm
                assetType={uploadAssetType}
                disabled={!selectedProjectId || uploadState === "loading"}
                files={uploadFiles}
                message={uploadMessage}
                onAssetTypeChange={setUploadAssetType}
                onFilesChange={setUploadFiles}
                onReplaceExistingChange={setReplaceExisting}
                onSubmit={handleUpload}
                replaceExisting={replaceExisting}
                state={uploadState}
              />
              <AssetTable
                assets={assets}
                emptyLabel={detailState === "loading" ? "Loading assets..." : "No assets registered for this project."}
                projectId={selectedProjectId}
              />
              <PaginationControls pagination={assetPagination} page={assetPage} onPageChange={setAssetPage} />
            </>
          )}
          {detailTab === "results" && (
            <AssetTable
              assets={results}
              emptyLabel={detailState === "loading" ? "Loading results..." : "No processed results registered for this project."}
              projectId={selectedProjectId}
            />
          )}
          {detailTab === "jobs" && <JobList jobs={selectedJobs} emptyLabel="No jobs found for the selected project." loading={detailState === "loading"} />}
        </section>
      </section>
    </main>
  );
}

function AssetUploadForm({
  assetType,
  disabled,
  files,
  message,
  onAssetTypeChange,
  onFilesChange,
  onReplaceExistingChange,
  onSubmit,
  replaceExisting,
  state
}: {
  assetType: string;
  disabled: boolean;
  files: File[];
  message: string;
  onAssetTypeChange: (value: string) => void;
  onFilesChange: (files: File[]) => void;
  onReplaceExistingChange: (value: boolean) => void;
  onSubmit: () => void;
  replaceExisting: boolean;
  state: LoadState;
}) {
  return (
    <div className="upload-strip">
      <label>
        <span>Asset type</span>
        <select disabled={disabled} onChange={(event) => onAssetTypeChange(event.target.value)} value={assetType}>
          {uploadAssetTypes.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>
      <label className="file-picker">
        <span>Files</span>
        <input
          disabled={disabled}
          multiple
          onChange={(event) => onFilesChange(Array.from(event.target.files || []))}
          type="file"
        />
      </label>
      <label className="check-row">
        <input checked={replaceExisting} disabled={disabled} onChange={(event) => onReplaceExistingChange(event.target.checked)} type="checkbox" />
        <span>Replace existing singleton assets</span>
      </label>
      <button disabled={disabled || files.length === 0} onClick={onSubmit} type="button">
        {state === "loading" ? "Uploading..." : `Upload ${files.length || ""}`.trim()}
      </button>
      {message && <p className={state === "error" ? "upload-message is-error" : "upload-message"}>{message}</p>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function JobList({ jobs, emptyLabel, loading }: { jobs: JobSummary[]; emptyLabel: string; loading: boolean }) {
  return (
    <div className="job-list">
      {jobs.map((job) => (
        <article className="job-row" key={job.id}>
          <div>
            <strong>{job.module || job.job_type}</strong>
            <span>{job.stage || job.detail || job.status}</span>
          </div>
          <meter min={0} max={100} value={Number(job.progress || 0)} />
        </article>
      ))}
      {loading && Array.from({ length: 4 }).map((_, index) => <div className="job-row skeleton" key={index} />)}
      {!loading && jobs.length === 0 && <p className="empty">{emptyLabel}</p>}
    </div>
  );
}

function AssetTable({ assets, emptyLabel, projectId }: { assets: ProjectAsset[]; emptyLabel: string; projectId: string }) {
  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Size</th>
            <th>Uploaded</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => (
            <tr key={asset.id}>
              <td>{asset.original_name}</td>
              <td>{asset.asset_type}</td>
              <td>{formatSize(asset.size)}</td>
              <td>{formatDate(asset.uploaded_at)}</td>
              <td>
                <div className="asset-actions">
                  <a href={projectAssetPreviewUrl(projectId, asset.id)} rel="noreferrer" target="_blank">
                    Preview
                  </a>
                  <a href={projectAssetDownloadUrl(projectId, asset.id)}>
                    Download
                  </a>
                </div>
              </td>
            </tr>
          ))}
          {assets.length === 0 && (
            <tr>
              <td colSpan={5}>{emptyLabel}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function PaginationControls({
  pagination,
  page,
  onPageChange
}: {
  pagination?: Pagination;
  page: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = pagination?.total_pages || 0;
  return (
    <div className="pagination-bar">
      <span>
        {pagination ? `${pagination.total} assets · page ${pagination.page} of ${Math.max(totalPages, 1)}` : "No pagination data"}
      </span>
      <div>
        <button disabled={page <= 1} onClick={() => onPageChange(Math.max(1, page - 1))} type="button">
          Previous
        </button>
        <button disabled={!totalPages || page >= totalPages} onClick={() => onPageChange(page + 1)} type="button">
          Next
        </button>
      </div>
    </div>
  );
}

function PlaceholderRows({ columns, rows }: { columns: number; rows: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <tr key={rowIndex}>
          {Array.from({ length: columns }).map((__, columnIndex) => (
            <td key={columnIndex}>
              <span className="line-skeleton" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

function formatSize(size: number) {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}
