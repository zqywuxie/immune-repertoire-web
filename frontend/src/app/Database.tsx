import { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Database as DbIcon } from "lucide-react";
import { useApi } from "../shared/hooks/useApi";
import {
  getProject,
  listProjectAssets,
  listProjectResults,
} from "../shared/api/projects";
import type { PaginationInfo } from "../shared/components/Pagination";
import { PageHeader } from "../shared/components/PageHeader";
import { Pagination } from "../shared/components/Pagination";
import { Tabs } from "../shared/components/Tabs";
import { EmptyState } from "../shared/components/EmptyState";
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
      </PageHeader>

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
