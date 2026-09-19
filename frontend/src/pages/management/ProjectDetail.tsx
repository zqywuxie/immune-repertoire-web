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
  { key: "overview", label: "概览" },
  { key: "assets", label: "文件" },
  { key: "results", label: "结果" },
  { key: "samples", label: "样本" },
  { key: "group-specs", label: "分组方案" },
  { key: "settings", label: "设置" },
];

const RESULT_PAGE_SIZE = 10;
const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const ANALYSIS_ASSET_TYPES = ["pep", "profile", "datapoint", "transcriptome", "expression", "deconvolution", "cibersort"];

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
          "更新项目失败"
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
          返回项目列表
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
            项目管理
          </button>
          {loadingProject ? (
            <Skeleton width="300px" height="36px" variant="text" />
          ) : (
            <PageHeader
              title={projectData?.name || "项目"}
              subtitle={
                projectData
                  ? `${projectData.institution || "未填写机构"} · ${projectData.sample_count || 0} 个样本 · ${projectData.result_count || 0} 项结果`
                  : undefined
              }
            />
          )}
        </div>
        {projectData && (
          <div style={{ display: "flex", gap: "var(--spacing-sm)" }}>
            <button
              onClick={() => navigate(`/analysis/center?project=${encodeURIComponent(projectId || "")}`)}
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
              分析
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
              编辑
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
              <h4 style={{ margin: 0, fontSize: "0.95rem" }}>分析数据集</h4>
              <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.82rem" }}>
                请根据所选分析准备克隆序列表和样本指标表；按需添加转录组数据。
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
              emptyLabel="尚未登记分析数据集。"
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
              emptyLabel="尚未上传项目文件。"
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
              分析结果（{analysisResults.length})
            </h4>
            <AssetTable
              assets={analysisResults}
              loading={loadingAssets || loadingResults}
              emptyLabel="尚未生成分析结果。"
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
          title="编辑项目"
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
        title="项目不存在"
        description="项目可能已删除，或当前账户没有访问权限。"
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
        <MetricCard icon={FileText} label="文件总数" value={totalAssets} color="var(--accent)" />
        <MetricCard icon={Boxes} label="样本" value={project.sample_count || 0} color="var(--success)" />
        <MetricCard icon={FlaskConical} label="结果" value={project.result_count || 0} color="var(--warning)" />
        <MetricCard icon={Layers} label="分组方案" value={project.group_spec_count || 0} color="var(--info)" />
      </div>

      {/* Quick actions */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--spacing-md)" }}>
        <Card onClick={() => onNavigate(`/analysis/center?project=${encodeURIComponent(projectId || "")}`)}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)" }}>
            <div style={{
              width: "44px", height: "44px", borderRadius: "var(--radius-control)",
              background: "color-mix(in srgb, var(--success) 15%, transparent)",
              color: "var(--success)", display: "grid", placeItems: "center", flexShrink: 0,
            }}>
              <FlaskConical size={22} />
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>开始分析</div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                进入分析中心，选择工具并使用当前项目的数据
              </div>
            </div>
          </div>
        </Card>
        <Card onClick={() => onNavigate(`/management/projects/${projectId}`)} ariaLabel="上传数据">
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)" }}>
            <div style={{
              width: "44px", height: "44px", borderRadius: "var(--radius-control)",
              background: "color-mix(in srgb, var(--accent) 15%, transparent)",
              color: "var(--accent)", display: "grid", placeItems: "center", flexShrink: 0,
            }}>
              <Upload size={22} />
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>上传数据</div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                添加克隆序列表、样本指标表及转录组数据
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
          <h3 style={{ margin: 0 }}>项目详情</h3>
          <StatusBadge status={project.status || "active"} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-md)", fontSize: "0.85rem" }}>
          <DetailField label="名称" value={project.name} />
          <DetailField label="所属机构" value={project.institution || "—"} />
          <DetailField label="合作类型" value={project.cooperation_level || "—"} />
          <DetailField label="状态" value={project.status || "active"} />
          <DetailField label="创建时间" value={project.created_at ? new Date(project.created_at).toLocaleDateString() : "—"} />
          <DetailField label="更新时间" value={project.updated_at ? new Date(project.updated_at).toLocaleDateString() : "—"} />
          {project.description && (
            <div style={{ gridColumn: "1 / -1" }}>
              <DetailField label="说明" value={project.description} />
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
          <h3 style={{ margin: "0 0 var(--spacing-md)" }}>数据文件概览</h3>
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
          title="暂无样本"
          description="当前项目尚未登记样本，可在样本管理中添加。"
        />
      </div>
    );
  }

  const columns = [
    "样本编号",
    "样本名称",
    "链类型",
    "物种",
    "Healthy",
    "Disease",
    "Tissue",
  ];

  return (
    <div style={{ marginTop: "var(--spacing-lg)" }}>
      <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "var(--spacing-md)" }}>
        {samples.length} 样本
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
        throw new Error((e as { detail?: string }).detail || (e as { message?: string }).message || "创建分组方案失败");
      }
      setNewSpecName("");
      setNewSpecGroups("");
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "创建失败");
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
        throw new Error((e as { detail?: string }).detail || (e as { message?: string }).message || "删除分组方案失败");
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
        <h4 style={{ margin: "0 0 var(--spacing-md)", fontSize: "0.9rem", fontWeight: 600 }}>创建分组方案</h4>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-md)" }}>
            <label className="field-label">
              名称 *
              <input
                type="text"
                value={newSpecName}
                onChange={(e) => setNewSpecName(e.target.value)}
                placeholder="例如：处理组与对照组"
                className="input"
                disabled={saving}
              />
            </label>
            <label className="field-label">
              分组（必填，多个值用逗号分隔）
              <input
                type="text"
                value={newSpecGroups}
                onChange={(e) => setNewSpecGroups(e.target.value)}
                placeholder="例如：健康组、疾病组"
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
              {saving ? "正在保存…" : "保存"}
            </button>
          </div>
        </div>
      </Card>

      {/* Existing specs */}
      {!hasSpecs ? (
        <EmptyState
          icon={Layers}
          title="暂无分组方案"
          description="分组方案定义样本的比较方式，创建后可用于分组统计与可视化。"
        />
      ) : (
        <div style={{ display: "grid", gap: "var(--spacing-md)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              {groupSpecs!.length} 分组方案 已定义
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
                        {specData.name || spec.name || `分组方案 ${idx + 1}`}
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
                        title="删除分组方案"
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
                          {typeof g === "string" ? g : g.name || g.label || `分组 ${gi + 1}`}
                        </span>
                      ))}
                    </div>
                  )}
                  <details style={{ fontSize: "0.8rem" }}>
                    <summary style={{ color: "var(--text-tertiary)", cursor: "pointer" }}>原始结构化数据</summary>
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
        title="项目尚未加载"
        description="项目不可用时无法显示设置。"
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
        throw new Error(e.detail || e.message || "保存失败");
      }
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
      onSaved();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "保存失败");
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
        <h3 style={{ margin: "0 0 var(--spacing-lg)" }}>编辑项目</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-md)" }}>
          <label className="field-label">
            项目名称（必填）
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} className="input" />
          </label>
          <label className="field-label">
            状态
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="select">
              <option value="active">进行中</option>
              <option value="paused">已暂停</option>
              <option value="archived">已归档</option>
            </select>
          </label>
          <label className="field-label">
            所属机构
            <input type="text" value={institution} onChange={(e) => setInstitution(e.target.value)} className="input" placeholder="例如：南华大学" />
          </label>
          <label className="field-label">
            合作类型
            <select value={cooperationLevel} onChange={(e) => setCooperationLevel(e.target.value)} className="select">
              <option value="">未设置</option>
              <option value="internal">内部</option>
              <option value="public">公开</option>
              <option value="collaboration">合作</option>
              <option value="restricted">受限</option>
            </select>
          </label>
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="field-label">
              说明
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} className="textarea" rows={3} placeholder="填写项目说明…" />
            </label>
          </div>
        </div>

        {saveError && <p style={{ margin: "var(--spacing-md) 0 0", color: "var(--danger)", fontSize: "0.85rem" }}>{saveError}</p>}

        <div style={{ display: "flex", gap: "var(--spacing-sm)", justifyContent: "flex-end", marginTop: "var(--spacing-lg)" }}>
          <button onClick={handleSave} disabled={saving || !name.trim()} className="btn btn-primary">
            <Save size={16} />
            {saving ? "正在保存…" : saveSuccess ? "Saved!" : "保存修改"}
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
        <h3 style={{ margin: "0 0 var(--spacing-md)", fontSize: "0.9rem", color: "var(--text-secondary)" }}>项目信息</h3>
        <div style={{ fontSize: "0.85rem", color: "var(--text-tertiary)", lineHeight: 1.8 }}>
          <div>项目编号： <code style={{ color: "var(--text-primary)" }}>{project.id || projectId}</code></div>
          <div>创建时间： {project.created_at ? new Date(project.created_at).toLocaleString() : "—"}</div>
          <div>更新时间： {project.updated_at ? new Date(project.updated_at).toLocaleString() : "—"}</div>
          <div>用户编号： {project.user_id ?? "—"}</div>
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
