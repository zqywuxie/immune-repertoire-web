import { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Database as DbIcon, Download } from "lucide-react";
import { useApi } from "../shared/hooks/useApi";
import {
  getProject,
  listProjectAssets,
  listProjectResults,
  projectExportUrl,
} from "../shared/api/projects";
import type { PaginationInfo } from "../shared/components/Pagination";
import { PageHeader } from "../shared/components/PageHeader";
import { Pagination } from "../shared/components/Pagination";
import { Tabs } from "../shared/components/Tabs";
import { EmptyState } from "../shared/components/EmptyState";
import { Skeleton } from "../shared/components/Skeleton";
import { AssetTable } from "../features/assets/AssetTable";
import { AssetUpload } from "../features/assets/AssetUpload";
import type { ProjectAsset } from "../shared/types/domain";

const ASSET_PAGE_SIZE = 10;

const TABS = [
  { key: "assets", label: "Assets" },
  { key: "results", label: "Results" },
];

export function DatabasePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState("assets");
  const [page, setPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0);
  const [exportOptions, setExportOptions] = useState({
    includeAssets: true,
    includeResults: true,
    includeGroupSpecs: true,
    includeManifest: true,
  });

  const projectState = useApi(
    () => (projectId ? getProject(projectId) : Promise.resolve(null)),
    [projectId, refreshKey]
  );
  const assetsState = useApi(
    () =>
      projectId
        ? listProjectAssets(projectId, {
            page,
            pageSize: ASSET_PAGE_SIZE,
          })
        : Promise.resolve({ assets: [] as ProjectAsset[], pagination: undefined }),
    [projectId, page, refreshKey]
  );
  const resultsState = useApi(
    () =>
      projectId
        ? listProjectResults(projectId, { page: 1, pageSize: 50 })
        : Promise.resolve({ success: true, results: [] as ProjectAsset[] }),
    [projectId, refreshKey]
  );

  const handleUploadSuccess = useCallback(() => {
    setPage(1);
    setRefreshKey((k) => k + 1);
  }, []);

  const toggleExportOption = (key: keyof typeof exportOptions) => {
    setExportOptions((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  if (!projectId) {
    return (
      <EmptyState
        icon={DbIcon}
        title="Select a Project"
        description="Choose a project from the Dashboard or navigate to a project URL."
        action={{ label: "Go to Dashboard", to: "/" }}
      />
    );
  }

  const project =
    projectState.status === "ready" ? projectState.data : null;
  const assets =
    assetsState.status === "ready" ? assetsState.data.assets : [];
  const pagination: PaginationInfo | undefined =
    assetsState.status === "ready"
      ? assetsState.data.pagination
      : undefined;
  const results =
    resultsState.status === "ready" ? resultsState.data.results : [];

  const loading = projectState.status === "loading";
  const error = projectState.status === "error" ? projectState.error : null;
  const assetsError = assetsState.status === "error" ? assetsState.error : null;
  const resultsError = resultsState.status === "error" ? resultsState.error : null;

  return (
    <>
      <PageHeader
        title={project?.name || "Loading…"}
        subtitle={
          project
            ? `${project.institution || "No institution"} · ${project.sample_count || 0} samples · ${project.result_count || 0} results`
            : "Project details"
        }
      >
        <button
          onClick={() => navigate("/")}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "8px 16px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--text-secondary)",
            fontWeight: 500,
            fontSize: "0.85rem",
          }}
        >
          <ArrowLeft size={16} />
          All Projects
        </button>
        <button
          onClick={() => window.open(projectExportUrl(projectId, exportOptions), "_blank")}
          disabled={!Object.values(exportOptions).some(Boolean)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "8px 16px",
            borderRadius: "var(--radius-control)",
            border: "none",
            background: Object.values(exportOptions).some(Boolean) ? "var(--accent)" : "var(--bg-inset)",
            color: Object.values(exportOptions).some(Boolean) ? "#fff" : "var(--text-tertiary)",
            fontWeight: 600,
            fontSize: "0.85rem",
            cursor: Object.values(exportOptions).some(Boolean) ? "pointer" : "not-allowed",
          }}
        >
          <Download size={16} />
          Export Project
        </button>
      </PageHeader>

      {/* Error banners */}
      {error && <div className="error-banner">⚠ {error}</div>}
      {assetsError && tab === "assets" && <div className="error-banner">⚠ {assetsError}</div>}
      {resultsError && tab === "results" && <div className="error-banner">⚠ {resultsError}</div>}

      {/* Project stats skeleton */}
      {loading && (
        <div style={{ display: "flex", gap: "var(--spacing-lg)" }}>
          <Skeleton height="24px" width="120px" variant="text" />
          <Skeleton height="24px" width="160px" variant="text" />
          <Skeleton height="24px" width="100px" variant="text" />
        </div>
      )}

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "var(--spacing-md)",
          padding: "var(--spacing-md)",
          border: "1px solid var(--separator)",
          borderRadius: "var(--radius-panel)",
          background: "var(--bg-elevated)",
        }}
      >
        <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--text-secondary)" }}>
          Export includes
        </span>
        <ExportCheckbox label="Assets" checked={exportOptions.includeAssets} onChange={() => toggleExportOption("includeAssets")} />
        <ExportCheckbox label="Results" checked={exportOptions.includeResults} onChange={() => toggleExportOption("includeResults")} />
        <ExportCheckbox label="Group specs" checked={exportOptions.includeGroupSpecs} onChange={() => toggleExportOption("includeGroupSpecs")} />
        <ExportCheckbox label="Manifest" checked={exportOptions.includeManifest} onChange={() => toggleExportOption("includeManifest")} />
      </div>

      <Tabs tabs={TABS} activeKey={tab} onChange={setTab} />

      {tab === "assets" && (
        <>
          <AssetUpload projectId={projectId} onSuccess={handleUploadSuccess} />
          <AssetTable
            assets={assets}
            loading={assetsState.status === "loading" || loading}
            emptyLabel="No assets registered for this project."
          />
          <Pagination
            pagination={pagination}
            onPageChange={setPage}
          />
        </>
      )}

      {tab === "results" && (
        <AssetTable
          assets={results}
          loading={resultsState.status === "loading" || loading}
          emptyLabel="No processed results for this project."
        />
      )}
    </>
  );
}

function ExportCheckbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        fontSize: "0.8rem",
        color: "var(--text-primary)",
        cursor: "pointer",
      }}
    >
      <input type="checkbox" checked={checked} onChange={onChange} />
      {label}
    </label>
  );
}
