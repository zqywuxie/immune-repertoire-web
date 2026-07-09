import { useState, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Boxes,
  FileText,
  FlaskConical,
  Layers,
  Settings2,
  AlertTriangle,
  Pencil,
  ArrowLeft,
  Database,
  Zap,
  Save,
  Upload,
  Users,
  Trash2,
  Plus,
} from "lucide-react";
import { useApi } from "../../shared/hooks/useApi";
import {
  getProject,
  listProjectAssets,
  listProjectResults,
} from "../../shared/api/projects";
import { listSamples } from "../../shared/api/samples";
import { PageHeader } from "../../shared/components/PageHeader";
import { Tabs } from "../../shared/components/Tabs";
import { MetricCard } from "../../shared/components/MetricCard";
import { Skeleton } from "../../shared/components/Skeleton";
import { EmptyState } from "../../shared/components/EmptyState";
import { Card } from "../../shared/components/Card";
import { AssetTable } from "../../features/assets/AssetTable";
import { AssetUpload } from "../../features/assets/AssetUpload";
import { ProjectFileUpload } from "../../features/assets/ProjectFileUpload";
import { isInputAsset } from "../../features/assets/assetSets";
import { Pagination } from "../../shared/components/Pagination";
import { Sheet } from "../../shared/components/Sheet";
import { ProjectForm } from "../../features/projects/ProjectForm";
import { StatusBadge } from "../../shared/components/StatusBadge";
import type { PaginationInfo } from "../../shared/components/Pagination";
import type { ProjectAsset, ProjectCreate } from "../../shared/types/domain";
import type { AssetListResponse } from "../../shared/api/projects";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "assets", label: "Assets" },
  { key: "results", label: "Results" },
  { key: "samples", label: "Samples" },
  { key: "group-specs", label: "Group Specs" },
  { key: "settings", label: "Settings" },
];

const RESULT_PAGE_SIZE = 10;
const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const ANALYSIS_ASSET_TYPES = ["pep", "profile", "datapoint", "transcriptome", "expression"];

export function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState("overview");
  const [resultPage, setResultPage] = useState(1);
  const [showEditSheet, setShowEditSheet] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const project = useApi(() => getProject(projectId!), [projectId, refreshKey]);
  const analysisAssets = useApi(
    () => listProjectAnalysisAssets(projectId!),
    [projectId, refreshKey]
  );
  const projectFiles = useApi(
    () => listProjectAssets(projectId!, { assetType: "project_file", page: 1, pageSize: 200 }),
    [projectId, refreshKey]
  );
  const resultAssetState = useApi(
    () => listProjectAssets(projectId!, { assetType: "processed_result", page: resultPage, pageSize: RESULT_PAGE_SIZE }),
    [projectId, resultPage, refreshKey]
  );
  const results = useApi(
    () => listProjectResults(projectId!, { page: resultPage, pageSize: RESULT_PAGE_SIZE }),
    [projectId, resultPage, refreshKey]
  );
  const samples = useApi(() => listSamples({ project_id: projectId! }), [projectId, refreshKey]);

  const projectData = project.status === "ready" ? project.data : null;
  const assetList = analysisAssets.status === "ready" ? analysisAssets.data.assets.filter(isInputAsset) : [];
  const projectFileList = projectFiles.status === "ready" ? projectFiles.data.assets : [];
  const resultAssets = resultAssetState.status === "ready" ? resultAssetState.data.assets : [];
  const resultList = results.status === "ready" ? results.data.results : [];
  const analysisResults = useMemo(() => {
    const byKey = new Map<string, typeof resultList[number]>();
    for (const asset of [...resultAssets, ...resultList]) {
      const key = asset.id || asset.storage_path || asset.original_name;
      byKey.set(key, asset);
    }
    return [...byKey.values()];
  }, [resultAssets, resultList]);
  const resultPagination = results.status === "ready" ? (results.data.pagination as PaginationInfo | undefined) : undefined;
  const sampleList = samples.status === "ready" ? samples.data.samples : [];

  const loadingProject = project.status === "loading";
  const loadingAssets = analysisAssets.status === "loading";
  const loadingProjectFiles = projectFiles.status === "loading";
  const loadingResults = results.status === "loading" || resultAssetState.status === "loading";
  const loadingSamples = samples.status === "loading";
  const projectError = project.status === "error" ? project.error : null;

  const handleRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1);
    setResultPage(1);
  }, []);

  const handleEditProject = async (data: ProjectCreate) => {
    const r = await fetch(`${API_BASE}/api/projects/${projectId}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(
        (e as { detail?: string }).detail ||
          (e as { message?: string }).message ||
          "Failed to update project"
      );
    }
    project.refetch();
  };

  if (projectError) {
    return (
      <>
        <ErrorBanner message={projectError} />
        <button
          onClick={() => navigate("/management/projects")}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            marginTop: "var(--spacing-lg)",
            padding: "8px 16px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
            cursor: "pointer",
          }}
        >
          <ArrowLeft size={16} />
          Back to Project Library
        </button>
      </>
    );
  }

  return (
    <>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "var(--spacing-lg)",
          flexWrap: "wrap",
        }}
      >
        <div>
          <button
            onClick={() => navigate("/management/projects")}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              padding: 0,
              border: "none",
              background: "transparent",
              color: "var(--text-secondary)",
              fontSize: "0.8rem",
              cursor: "pointer",
              marginBottom: "4px",
            }}
          >
            <ArrowLeft size={14} />
            Project Library
          </button>
          {loadingProject ? (
            <Skeleton width="300px" height="36px" variant="text" />
          ) : (
            <PageHeader
              title={projectData?.name || "Project"}
              subtitle={
                projectData
                  ? `${projectData.institution || "No institution"} · ${projectData.sample_count || 0} samples · ${projectData.result_count || 0} results`
                  : undefined
              }
            />
          )}
        </div>
        {projectData && (
          <div style={{ display: "flex", gap: "var(--spacing-sm)" }}>
            <button
              onClick={() => navigate(`/analysis/script-hub?project=${projectId}`)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 16px",
                borderRadius: "var(--radius-control)",
                background: "var(--success)",
                color: "#fff",
                fontSize: "0.85rem",
                fontWeight: 500,
                border: "none",
                cursor: "pointer",
              }}
            >
              <Zap size={16} />
              Analyze
            </button>
            <button
              onClick={() => setShowEditSheet(true)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 16px",
                borderRadius: "var(--radius-control)",
                border: "1px solid var(--separator)",
                background: "var(--bg-elevated)",
                color: "var(--text-primary)",
                fontSize: "0.85rem",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              <Pencil size={16} />
              Edit
            </button>
          </div>
        )}
      </div>

      {/* Tabs */}
      <Tabs tabs={TABS} activeKey={activeTab} onChange={setActiveTab} />

      {/* Tab content */}
      {activeTab === "overview" && (
        <OverviewTab
          project={projectData}
          loading={loadingProject}
          onNavigate={navigate}
          projectId={projectId}
        />
      )}

      {activeTab === "assets" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
          <section style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
            <div>
              <h4 style={{ margin: 0, fontSize: "0.95rem" }}>Analysis Data Sets</h4>
              <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.82rem" }}>
                Required analysis inputs are PEP paths and Profile. Transcriptome data is optional.
              </p>
            </div>
            {projectId && (
              <AssetUpload
                projectId={projectId}
                onSuccess={handleRefresh}
              />
            )}
            <AssetTable
              assets={assetList}
              loading={loadingAssets}
              emptyLabel="No analysis data sets registered yet."
              projectId={projectId}
              onAssetDeleted={handleRefresh}
              showGroup
            />
          </section>
          <section style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
            {projectId && (
              <ProjectFileUpload
                projectId={projectId}
                onSuccess={handleRefresh}
              />
            )}
            <AssetTable
              assets={projectFileList}
              loading={loadingProjectFiles}
              emptyLabel="No project files uploaded yet."
              projectId={projectId}
              onAssetDeleted={handleRefresh}
              showGroup={false}
            />
          </section>
        </div>
      )}

      {activeTab === "results" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
          <div>
            <h4 style={{ margin: "0 0 var(--spacing-sm)", fontSize: "0.85rem", color: "var(--text-secondary)", fontWeight: 600 }}>
              Analysis Results ({analysisResults.length})
            </h4>
            <AssetTable
              assets={analysisResults}
              loading={loadingAssets || loadingResults}
              emptyLabel="No analysis results generated yet."
              projectId={projectId}
              onAssetDeleted={handleRefresh}
              showSelect={false}
              showStatus
            />
          </div>
          <Pagination
            pagination={resultPagination}
            onPageChange={setResultPage}
          />
        </div>
      )}

      {activeTab === "samples" && (
        <SamplesTab
          samples={sampleList}
          loading={loadingSamples}
          projectId={projectId}
        />
      )}

      {activeTab === "group-specs" && (
        <GroupSpecsTab
          groupSpecs={projectData?.group_specs}
          loading={loadingProject}
          projectId={projectId}
        />
      )}

      {activeTab === "settings" && (
        <SettingsTab
          project={projectData}
          loading={loadingProject}
          projectId={projectId}
          onSaved={() => project.refetch()}
        />
      )}

      {/* Edit project sheet */}
      {projectData && (
        <ProjectForm
          open={showEditSheet}
          onClose={() => setShowEditSheet(false)}
          onSubmit={handleEditProject}
          initial={{
            name: projectData.name ?? "",
            institution: projectData.institution ?? undefined,
            cooperation_level: projectData.cooperation_level ?? undefined,
            description: projectData.description ?? undefined,
            status: projectData.status ?? "active",
          }}
          title="Edit Project"
        />
      )}
    </>
  );
}

async function listProjectAnalysisAssets(projectId: string): Promise<AssetListResponse> {
  const responses = await Promise.all(
    ANALYSIS_ASSET_TYPES.map((assetType) =>
      listProjectAssets(projectId, { assetType, page: 1, pageSize: 200 }),
    ),
  );
  const byId = new Map<string, ProjectAsset>();
  for (const response of responses) {
    for (const asset of response.assets) {
      byId.set(asset.id || `${asset.asset_type}:${asset.storage_path}:${asset.original_name}`, asset);
    }
  }
  const assets = [...byId.values()].sort((a, b) => {
    const at = new Date(a.uploaded_at || 0).getTime();
    const bt = new Date(b.uploaded_at || 0).getTime();
    return bt - at;
  });
  return {
    assets,
    pagination: {
      page: 1,
      page_size: assets.length,
      total: assets.length,
      total_pages: assets.length ? 1 : 0,
    },
  };
}

/* ── Overview Tab ───────────────────────────────────────────────────── */

function OverviewTab({
  project,
  loading,
  onNavigate,
  projectId,
}: {
  project: Record<string, any> | null;
  loading: boolean;
  onNavigate: (to: string) => void;
  projectId?: string;
}) {
  if (loading) {
    return (
      <div style={{ display: "grid", gap: "var(--spacing-md)", marginTop: "var(--spacing-lg)" }}>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} height="80px" />
        ))}
      </div>
    );
  }

  if (!project) {
    return (
      <EmptyState
        icon={Database}
        title="Project not found"
        description="This project may have been deleted or you may not have access."
      />
    );
  }

  const totalAssets = Object.values(project.asset_counts || {}).reduce((s: number, c: any) => s + Number(c), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)", marginTop: "var(--spacing-lg)" }}>
      {/* Metric cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "var(--spacing-md)",
        }}
      >
        <MetricCard icon={FileText} label="Total Assets" value={totalAssets} color="var(--accent)" />
        <MetricCard icon={Boxes} label="Samples" value={project.sample_count || 0} color="var(--success)" />
        <MetricCard icon={FlaskConical} label="Results" value={project.result_count || 0} color="var(--warning)" />
        <MetricCard icon={Layers} label="Group Specs" value={project.group_spec_count || 0} color="var(--info)" />
      </div>

      {/* Quick actions */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--spacing-md)" }}>
        <Card onClick={() => onNavigate(`/analysis/script-hub?project=${projectId}`)}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)" }}>
            <div style={{
              width: "44px", height: "44px", borderRadius: "var(--radius-control)",
              background: "color-mix(in srgb, var(--success) 15%, transparent)",
              color: "var(--success)", display: "grid", placeItems: "center", flexShrink: 0,
            }}>
              <FlaskConical size={22} />
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>Run Analysis</div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                Open ScriptHub to configure and execute analysis pipelines
              </div>
            </div>
          </div>
        </Card>
        <Card onClick={() => onNavigate(`/management/projects/${projectId}`)} ariaLabel="Upload assets">
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)" }}>
            <div style={{
              width: "44px", height: "44px", borderRadius: "var(--radius-control)",
              background: "color-mix(in srgb, var(--accent) 15%, transparent)",
              color: "var(--accent)", display: "grid", placeItems: "center", flexShrink: 0,
            }}>
              <Upload size={22} />
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>Upload Assets</div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                Add PEP files, profiles, and transcriptome data
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Project details card */}
      <div
        style={{
          background: "var(--bg-elevated)",
          borderRadius: "var(--radius-card)",
          padding: "var(--spacing-xl)",
          boxShadow: "var(--shadow-sm)",
          border: "1px solid var(--separator)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)", marginBottom: "var(--spacing-md)" }}>
          <h3 style={{ margin: 0 }}>Project Details</h3>
          <StatusBadge status={project.status || "active"} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-md)", fontSize: "0.85rem" }}>
          <DetailField label="Name" value={project.name} />
          <DetailField label="Institution" value={project.institution || "—"} />
          <DetailField label="Cooperation Level" value={project.cooperation_level || "—"} />
          <DetailField label="Status" value={project.status || "active"} />
          <DetailField label="Created" value={project.created_at ? new Date(project.created_at).toLocaleDateString() : "—"} />
          <DetailField label="Updated" value={project.updated_at ? new Date(project.updated_at).toLocaleDateString() : "—"} />
          {project.description && (
            <div style={{ gridColumn: "1 / -1" }}>
              <DetailField label="Description" value={project.description} />
            </div>
          )}
        </div>
      </div>

      {/* Asset type breakdown */}
      {project.asset_counts && Object.keys(project.asset_counts).length > 0 && (
        <div
          style={{
            background: "var(--bg-elevated)",
            borderRadius: "var(--radius-card)",
            padding: "var(--spacing-xl)",
            boxShadow: "var(--shadow-sm)",
            border: "1px solid var(--separator)",
          }}
        >
          <h3 style={{ margin: "0 0 var(--spacing-md)" }}>Asset Breakdown</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "var(--spacing-md)" }}>
            {Object.entries(project.asset_counts).map(([type, count]) => (
              <div key={type} style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--accent)" }}>
                  {String(count as number)}
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", textTransform: "capitalize" }}>
                  {type.replace(/_/g, " ")}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Samples Tab ─────────────────────────────────────────────────────── */

function SamplesTab({
  samples,
  loading,
  projectId,
}: {
  samples: any[];
  loading: boolean;
  projectId?: string;
}) {
  if (loading) {
    return (
      <div style={{ marginTop: "var(--spacing-lg)" }}>
        <Skeleton height="200px" />
      </div>
    );
  }

  if (!samples || samples.length === 0) {
    return (
      <div style={{ marginTop: "var(--spacing-lg)" }}>
        <EmptyState
          icon={Users}
          title="No samples registered"
          description="No samples have been registered for this project yet. Samples can be added via the Sample Registry."
        />
      </div>
    );
  }

  const columns = [
    "Sample ID",
    "Sample Name",
    "Chain",
    "Species",
    "Healthy",
    "Disease",
    "Tissue",
  ];

  return (
    <div style={{ marginTop: "var(--spacing-lg)" }}>
      <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "var(--spacing-md)" }}>
        {samples.length} sample{samples.length !== 1 ? "s" : ""}
      </div>
      <Card>
        <div style={{ overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "600px" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--separator)" }}>
                {columns.map((h) => (
                  <th
                    key={h}
                    scope="col"
                    style={{
                      textAlign: "left",
                      padding: "10px 14px",
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
              {samples.map((s: any, idx: number) => (
                <tr
                  key={s.id || idx}
                  style={{ borderBottom: "1px solid var(--separator)" }}
                >
                  <td style={sampleCellStyle}>
                    <code style={{ fontSize: "0.8rem", background: "var(--bg-inset)", padding: "2px 6px", borderRadius: "4px" }}>
                      {s.sample_id || "—"}
                    </code>
                  </td>
                  <td style={{ ...sampleCellStyle, maxWidth: "160px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {s.sample_name || "—"}
                  </td>
                  <td style={sampleCellStyle}>
                    <span style={sampleChipStyle}>{s.chain_flag || "—"}</span>
                  </td>
                  <td style={sampleCellStyle}>{s.spices || "—"}</td>
                  <td style={sampleCellStyle}>
                    <span
                      style={{
                        ...sampleChipStyle,
                        background: s.is_healthy === "yes" ? "rgba(52,199,89,0.12)" : s.is_healthy === "no" ? "rgba(255,59,48,0.12)" : "var(--bg-inset)",
                        color: s.is_healthy === "yes" ? "var(--success)" : s.is_healthy === "no" ? "var(--danger)" : "var(--text-secondary)",
                      }}
                    >
                      {s.is_healthy || "—"}
                    </span>
                  </td>
                  <td style={{ ...sampleCellStyle, maxWidth: "120px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {s.illness || "—"}
                  </td>
                  <td style={sampleCellStyle}>{s.iso_tag || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* ── Group Specs Tab ────────────────────────────────────────────────── */

function GroupSpecsTab({
  groupSpecs,
  loading,
  projectId,
}: {
  groupSpecs?: unknown[];
  loading: boolean;
  projectId?: string;
}) {
  const [newSpecName, setNewSpecName] = useState("");
  const [newSpecGroups, setNewSpecGroups] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [deletingIdx, setDeletingIdx] = useState<number | null>(null);

  const handleCreate = async () => {
    if (!projectId || !newSpecName.trim()) return;
    setSaving(true);
    setSaveError("");
    try {
      const groups = newSpecGroups
        .split(",")
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      const r = await fetch(`${API_BASE}/api/projects/${projectId}/group-specs`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newSpecName.trim(), groups }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error((e as { detail?: string }).detail || (e as { message?: string }).message || "Failed to create group spec");
      }
      setNewSpecName("");
      setNewSpecGroups("");
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (specIndex: number) => {
    if (!projectId) return;
    setDeletingIdx(specIndex);
    try {
      const r = await fetch(`${API_BASE}/api/projects/${projectId}/group-specs/${specIndex}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error((e as { detail?: string }).detail || (e as { message?: string }).message || "Failed to delete group spec");
      }
      setRefreshKey((k) => k + 1);
    } catch (err) {
      // silently fail, user sees the delete button restore
    } finally {
      setDeletingIdx(null);
    }
  };

  if (loading) {
    return (
      <div style={{ marginTop: "var(--spacing-lg)" }}>
        <Skeleton height="200px" />
      </div>
    );
  }

  const hasSpecs = groupSpecs && groupSpecs.length > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)", marginTop: "var(--spacing-lg)" }}>
      {/* Create form */}
      <Card>
        <h4 style={{ margin: "0 0 var(--spacing-md)", fontSize: "0.9rem", fontWeight: 600 }}>Create Group Spec</h4>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-md)" }}>
            <label className="field-label">
              Name *
              <input
                type="text"
                value={newSpecName}
                onChange={(e) => setNewSpecName(e.target.value)}
                placeholder="e.g. Treatment vs Control"
                className="input"
                disabled={saving}
              />
            </label>
            <label className="field-label">
              Groups (comma-separated) *
              <input
                type="text"
                value={newSpecGroups}
                onChange={(e) => setNewSpecGroups(e.target.value)}
                placeholder="e.g. Healthy, Disease"
                className="input"
                disabled={saving}
              />
            </label>
          </div>
          {saveError && (
            <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--danger)" }}>{saveError}</p>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              onClick={handleCreate}
              disabled={saving || !newSpecName.trim() || !newSpecGroups.trim()}
              className="btn btn-primary"
            >
              <Plus size={16} />
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </Card>

      {/* Existing specs */}
      {!hasSpecs ? (
        <EmptyState
          icon={Layers}
          title="No group specs defined"
          description="Group specifications define how samples are organized for comparative analysis. Create group specs to enable grouped statistical analysis and visualization."
        />
      ) : (
        <div style={{ display: "grid", gap: "var(--spacing-md)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              {groupSpecs!.length} group spec{groupSpecs!.length !== 1 ? "s" : ""} defined
            </span>
          </div>
          {groupSpecs!.map((spec: any, idx: number) => {
            const groups = Array.isArray(spec.groups) ? spec.groups : Array.isArray(spec.spec_json?.groups) ? spec.spec_json.groups : [];
            const specData = spec.spec_json || spec;
            return (
              <Card key={spec.id || idx}>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>
                        {specData.name || spec.name || `Group Spec ${idx + 1}`}
                      </div>
                      {specData.description && (
                        <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                          {specData.description}
                        </div>
                      )}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
                      {spec.created_at && (
                        <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                          {new Date(spec.created_at).toLocaleDateString()}
                        </span>
                      )}
                      <button
                        onClick={() => handleDelete(idx)}
                        disabled={deletingIdx === idx}
                        title="Delete group spec"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                          padding: "5px 10px",
                          borderRadius: "var(--radius-control)",
                          border: "1px solid var(--separator)",
                          background: "transparent",
                          color: "var(--danger)",
                          fontSize: "0.78rem",
                          fontWeight: 500,
                          cursor: "pointer",
                          whiteSpace: "nowrap",
                        }}
                      >
                        <Trash2 size={14} />
                        {deletingIdx === idx ? "Deleting…" : "Delete"}
                      </button>
                    </div>
                  </div>
                  {groups.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
                      {groups.map((g: any, gi: number) => (
                        <span
                          key={gi}
                          style={{
                            padding: "3px 10px",
                            borderRadius: "var(--radius-pill)",
                            background: "color-mix(in srgb, var(--accent) 10%, transparent)",
                            color: "var(--accent)",
                            fontSize: "0.78rem",
                            fontWeight: 500,
                            border: "1px solid color-mix(in srgb, var(--accent) 20%, transparent)",
                          }}
                        >
                          {typeof g === "string" ? g : g.name || g.label || `Group ${gi + 1}`}
                        </span>
                      ))}
                    </div>
                  )}
                  <details style={{ fontSize: "0.8rem" }}>
                    <summary style={{ color: "var(--text-tertiary)", cursor: "pointer" }}>Raw JSON</summary>
                    <pre
                      style={{
                        margin: "var(--spacing-sm) 0 0",
                        padding: "var(--spacing-md)",
                        borderRadius: "var(--radius-control)",
                        background: "var(--bg-root)",
                        fontSize: "0.78rem",
                        overflow: "auto",
                        maxHeight: "200px",
                        fontFamily: "var(--font-mono, monospace)",
                      }}
                    >
                      {JSON.stringify(specData, null, 2)}
                    </pre>
                  </details>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ── Settings Tab ───────────────────────────────────────────────────── */

function SettingsTab({
  project,
  loading,
  projectId,
  onSaved,
}: {
  project: Record<string, any> | null;
  loading: boolean;
  projectId?: string;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [status, setStatus] = useState("active");
  const [cooperationLevel, setCooperationLevel] = useState("");
  const [institution, setInstitution] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Init form when project loads
  const [initialized, setInitialized] = useState(false);
  if (project && !initialized) {
    setName(project.name || "");
    setStatus(project.status || "active");
    setCooperationLevel(project.cooperation_level || "");
    setInstitution(project.institution || "");
    setDescription(project.description || "");
    setInitialized(true);
  }

  if (loading) {
    return (
      <div style={{ marginTop: "var(--spacing-lg)" }}>
        <Skeleton height="300px" />
      </div>
    );
  }

  if (!project) {
    return (
      <EmptyState
        icon={Settings2}
        title="Project not loaded"
        description="Cannot display settings while the project is unavailable."
      />
    );
  }

  const handleSave = async () => {
    setSaving(true);
    setSaveError("");
    setSaveSuccess(false);
    try {
      const r = await fetch(`${API_BASE}/api/projects/${projectId}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          status,
          cooperation_level: cooperationLevel.trim() || null,
          institution: institution.trim() || null,
          description: description.trim() || null,
        }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || e.message || "Failed to save");
      }
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
      onSaved();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)", marginTop: "var(--spacing-lg)" }}>
      {/* Editable settings form */}
      <div
        style={{
          background: "var(--bg-elevated)",
          borderRadius: "var(--radius-card)",
          padding: "var(--spacing-xl)",
          boxShadow: "var(--shadow-sm)",
          border: "1px solid var(--separator)",
        }}
      >
        <h3 style={{ margin: "0 0 var(--spacing-lg)" }}>Edit Project</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-md)" }}>
          <label className="field-label">
            Project Name *
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} className="input" />
          </label>
          <label className="field-label">
            Status
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="select">
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="archived">Archived</option>
            </select>
          </label>
          <label className="field-label">
            Institution
            <input type="text" value={institution} onChange={(e) => setInstitution(e.target.value)} className="input" placeholder="e.g. Tsinghua University" />
          </label>
          <label className="field-label">
            Cooperation Level
            <select value={cooperationLevel} onChange={(e) => setCooperationLevel(e.target.value)} className="select">
              <option value="">— None —</option>
              <option value="internal">Internal</option>
              <option value="public">Public</option>
              <option value="collaboration">Collaboration</option>
              <option value="restricted">Restricted</option>
            </select>
          </label>
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="field-label">
              Description
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} className="textarea" rows={3} placeholder="Project description…" />
            </label>
          </div>
        </div>

        {saveError && <p style={{ margin: "var(--spacing-md) 0 0", color: "var(--danger)", fontSize: "0.85rem" }}>{saveError}</p>}

        <div style={{ display: "flex", gap: "var(--spacing-sm)", justifyContent: "flex-end", marginTop: "var(--spacing-lg)" }}>
          <button onClick={handleSave} disabled={saving || !name.trim()} className="btn btn-primary">
            <Save size={16} />
            {saving ? "Saving…" : saveSuccess ? "Saved!" : "Save Changes"}
          </button>
        </div>
      </div>

      {/* Read-only metadata */}
      <div
        style={{
          background: "var(--bg-elevated)",
          borderRadius: "var(--radius-card)",
          padding: "var(--spacing-xl)",
          boxShadow: "var(--shadow-sm)",
          border: "1px solid var(--separator)",
        }}
      >
        <h3 style={{ margin: "0 0 var(--spacing-md)", fontSize: "0.9rem", color: "var(--text-secondary)" }}>Project Metadata</h3>
        <div style={{ fontSize: "0.85rem", color: "var(--text-tertiary)", lineHeight: 1.8 }}>
          <div>Project ID: <code style={{ color: "var(--text-primary)" }}>{project.id || projectId}</code></div>
          <div>Created: {project.created_at ? new Date(project.created_at).toLocaleString() : "—"}</div>
          <div>Updated: {project.updated_at ? new Date(project.updated_at).toLocaleString() : "—"}</div>
          <div>User ID: {project.user_id ?? "—"}</div>
        </div>
      </div>
    </div>
  );
}

/* ── Reusable helpers ───────────────────────────────────────────────── */

function DetailField({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "2px" }}>
        {label}
      </div>
      <div style={{ color: "var(--text-primary)" }}>{value}</div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <>
      <dt style={{ fontWeight: 600, color: "var(--text-primary)", marginTop: "var(--spacing-sm)" }}>{label}</dt>
      <dd style={{ margin: "2px 0 0", color: "var(--text-secondary)" }}>{value}</dd>
    </>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--spacing-sm)",
        padding: "var(--spacing-md) var(--spacing-lg)",
        borderRadius: "var(--radius-panel)",
        background: "var(--danger)",
        color: "#fff",
        fontSize: "0.85rem",
        fontWeight: 500,
      }}
    >
      <AlertTriangle size={18} />
      {message}
    </div>
  );
}

/* ── Styles ─────────────────────────────────────────────────────────── */

const sampleCellStyle: React.CSSProperties = {
  padding: "10px 14px",
  fontSize: "0.85rem",
  color: "var(--text-primary)",
};

const sampleChipStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 8px",
  borderRadius: "var(--radius-pill)",
  background: "var(--bg-inset)",
  fontSize: "0.75rem",
  color: "var(--text-secondary)",
};
