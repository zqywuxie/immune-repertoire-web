import { useAssetSelection } from "../../features/assets/useAssetSelection";
import { ProjectDataScope } from "../../features/projects/ProjectDataScope";
import { DataReadError } from "../../features/assets/DataReadError";
import { ProjectResultFilters } from "../../features/results/ProjectResultFilters";
import { projectCatalogReturnPath } from "../../features/projects/catalogNavigation";
import { ProjectGroupSpecs } from "../../features/projects/ProjectGroupSpecs";
import { useState, useCallback, useEffect, useLayoutEffect } from "react";
import { useParams, useNavigate, useSearchParams, useLocation } from "react-router-dom";
import { apiClient } from "../../shared/api/client";
import { UnsavedChangesGuard } from "../../shared/components/UnsavedChangesGuard";
import { ProjectDatasetManager } from "../../features/assets/ProjectDatasetManager";
import { ProjectInputSamples } from "../../features/assets/ProjectInputSamples";
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
import { PageHeader } from "../../shared/components/PageHeader";
import { Tabs } from "../../shared/components/Tabs";
import { MetricCard } from "../../shared/components/MetricCard";
import { Skeleton } from "../../shared/components/Skeleton";
import { EmptyState } from "../../shared/components/EmptyState";
import { Card } from "../../shared/components/Card";
import { AssetTable, assetTypeLabels } from "../../features/assets/AssetTable";
import { ProjectFileUpload } from "../../features/assets/ProjectFileUpload";
import { Pagination } from "../../shared/components/Pagination";
import { Sheet } from "../../shared/components/Sheet";
import { ProjectForm } from "../../features/projects/ProjectForm";
import { StatusBadge } from "../../shared/components/StatusBadge";
import type { PaginationInfo } from "../../shared/components/Pagination";
import type { ProjectCreate } from "../../shared/types/domain";

const TABS = [
  { key: "overview", label: "概览" },
  { key: "assets", label: "数据集" },
  { key: "samples", label: "样本" },
  { key: "group-specs", label: "分组方案" },
  { key: "results", label: "分析结果" },
  { key: "attachments", label: "项目附件", secondary: true },
  { key: "settings", label: "设置", secondary: true },
];

const RESULT_PAGE_SIZE = 10;
const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const catalogReturnPath = projectCatalogReturnPath(useLocation().state);

  const [query, setQuery] = useSearchParams();
  const activeTab = TABS.some(tab => tab.key === query.get('tab')) ? query.get('tab')! : 'overview';
  const [uploadDrafts, setUploadDrafts] = useState(0);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [groupDraft, setGroupDraft] = useState(false);
  const [sampleDraft, setSampleDraft] = useState(false);
  const [inputFileDraft, setInputFileDraft] = useState(false);
  const [attachmentDraft, setAttachmentDraft] = useState(false);
  const [settingsDraft, setSettingsDraft] = useState(false);
  const [projectFormDraft, setProjectFormDraft] = useState(false);
  useEffect(() => { setUploadDrafts(0); setUploadBusy(false); setGroupDraft(false); setSampleDraft(false); setInputFileDraft(false); setAttachmentDraft(false); setAttachmentUploadCount(0); setAttachmentBusy(false); setShowAttachmentUpload(false); setDiscardAttachmentUpload(false); setSettingsDraft(false); setProjectFormDraft(false); }, [projectId]);
  const [dataProject, setDataProject] = useState(activeTab === "assets" ? projectId : "");
  useEffect(() => { if (activeTab === "assets") setDataProject(projectId); }, [activeTab, projectId]);
  const setActiveTab = (tab: string) => setQuery(previous => { const next = new URLSearchParams(previous); next.set('tab', tab); return next; });
  const attachmentSelection = useAssetSelection(JSON.stringify([projectId,"attachments"]));
  const attachmentPage = Math.max(1, Number(query.get('attachment_page')) || 1);
  const [showAttachmentUpload, setShowAttachmentUpload] = useState(false);
  const [attachmentBusy, setAttachmentBusy] = useState(false);
  const [attachmentUploadCount, setAttachmentUploadCount] = useState(0);
  const [attachmentUploadRevision, setAttachmentUploadRevision] = useState(0);
  const [discardAttachmentUpload, setDiscardAttachmentUpload] = useState(false);
  const resultDataset=query.get("result_dataset") || "";
  const resultType=query.get("result_type") || "";
  const resultJob=query.get("result_job") || "";
  const resultUnscoped=query.get("result_unscoped")==="1";
  const resultPage = Math.max(1, Math.floor(Number(query.get('result_page')) || 1));
  const setResultPage = (page: number) => setQuery(previous => { const next = new URLSearchParams(previous); page > 1 ? next.set('result_page', String(page)) : next.delete('result_page'); return next; });
  const [showEditSheet, setShowEditSheet] = useState(false);
  const [fullProjectTitle, setFullProjectTitle] = useState(false);
  useEffect(()=>setFullProjectTitle(false),[projectId]);
  const [refreshKey, setRefreshKey] = useState(0);

  const project = useApi(() => getProject(projectId!, { summaryOnly: true, includeGroupSpecs: false }), [projectId, refreshKey]);
  const attachmentRequest = JSON.stringify([projectId,refreshKey,attachmentPage]);
  const projectFiles = useApi(
    async () => ({...await listProjectAssets(projectId!, { assetType: "project_file", page: attachmentPage, pageSize: 50 }),request:attachmentRequest}),
    [projectId, refreshKey, attachmentPage], activeTab === "attachments"
  );
  const results = useApi(
    () => listProjectResults(projectId!, { page: resultPage, pageSize: RESULT_PAGE_SIZE, assetSet:resultDataset, analysisType:resultType, jobId:resultJob, unscoped:resultUnscoped }),
    [projectId, resultPage, refreshKey, resultDataset, resultType, resultJob, resultUnscoped], activeTab === "results"
  );
  useEffect(() => {
    if(projectFiles.status!=="ready" || !projectFiles.data.pagination || projectFiles.data.pagination.page!==attachmentPage)return;
    const last=Math.max(1,projectFiles.data.pagination.total_pages);
    if(attachmentPage>last)setQuery(previous=>{const next=new URLSearchParams(previous);last>1?next.set("attachment_page",String(last)):next.delete("attachment_page");return next;},{replace:true});
  },[projectFiles.status,projectFiles.status==="ready"?projectFiles.data.pagination:null,attachmentPage,setQuery]);
  useEffect(() => {
    if (activeTab !== "results" || results.status !== "ready" || results.data.pagination?.page !== resultPage) return;
    const lastPage = Math.max(1, results.data.pagination.total_pages);
    if (resultPage > lastPage) setQuery(previous => {
      const next = new URLSearchParams(previous);
      lastPage > 1 ? next.set("result_page", String(lastPage)) : next.delete("result_page");
      return next;
    }, { replace: true });
  }, [activeTab, results.status, results.status === "ready" ? results.data.pagination : null, resultPage, setQuery]);
  const projectData = project.status === "ready" ? project.data : null;
  const attachmentPageReady = projectFiles.status === "ready" && projectFiles.data.request === attachmentRequest;
  const projectFileList = projectFiles.status === "ready" && attachmentPageReady ? projectFiles.data.assets : [];
  const analysisResults = results.status === "ready" ? results.data.results : [];
  const resultPagination = results.status === "ready" ? (results.data.pagination as PaginationInfo | undefined) : undefined;

  const loadingProject = project.status === "loading";
  const loadingProjectFiles = projectFiles.status === "loading" || projectFiles.status === "idle" || (projectFiles.status === "ready" && !attachmentPageReady);
  const loadingResults = results.status === "loading" || results.status === "idle";
  const projectError = project.status === "error" ? project.error : null;

  const handleRefresh = useCallback(() => {
    apiClient.invalidateCache();
    setRefreshKey((k) => k + 1);
    setQuery(previous => { const next = new URLSearchParams(previous); next.delete('result_page'); return next; });
  }, [setQuery]);

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
    handleRefresh();
  };

  if (projectError) {
    return (
      <>
        <DataReadError title="项目暂时无法读取" message={projectError} onRetry={project.refetch} retryLabel="重新读取项目"/>
        <button
          onClick={() => navigate(catalogReturnPath)}
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
      <div className="data-project-heading"
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "var(--spacing-lg)",
          flexWrap: "wrap",
        }}
      >
        <div className={`data-project-title${fullProjectTitle?" is-expanded":""}`}>
          <button
            onClick={() => navigate(catalogReturnPath)}
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
                  ? `项目总计 · ${projectData.input_sample_count || 0} 个输入样本条目 · ${projectData.registered_sample_count || 0} 条登记 · ${projectData.result_count || 0} 项结果`
                  : undefined
              }
            />
          )}
          {(projectData?.name?.length || 0)>32 && <button className="data-project-title-toggle" aria-expanded={fullProjectTitle} onClick={()=>setFullProjectTitle(!fullProjectTitle)}>{fullProjectTitle?"收起项目名称":"展开完整项目名称"}</button>}
          <p className="data-project-scope">{activeTab === "overview" ? "项目概览 · 全部数据集" : activeTab === "attachments" ? "当前内容：项目全部附件" : activeTab === "results" ? (resultDataset || resultType || resultJob || resultUnscoped ? "当前内容：按筛选查看项目分析结果" : "当前内容：项目全部分析结果") : query.get("asset_set")?`当前数据集：${query.get("asset_set")}`:"当前范围：全部数据集"}</p>
        </div>
        {projectData && (
          <div className="data-project-actions">
            <button className="btn btn-secondary" onClick={()=>navigate(`/analysis/center?project=${encodeURIComponent(projectId || "")}&asset_set=${encodeURIComponent(query.get("asset_set") || "")}`)}><Zap size={16}/>进入分析</button>
            <button className="btn btn-secondary" onClick={()=>setShowEditSheet(true)}><Pencil size={16}/>编辑项目</button>
          </div>
        )}
      </div>

      <UnsavedChangesGuard when={uploadDrafts > 0 || uploadBusy || attachmentUploadCount > 0 || attachmentBusy || groupDraft || sampleDraft || inputFileDraft || attachmentDraft || settingsDraft || projectFormDraft}
        queryKeys={[...(groupDraft || sampleDraft || inputFileDraft || attachmentDraft || settingsDraft || projectFormDraft ? ["tab", "asset_set"] : []),
          ...(inputFileDraft ? ["file_page", "file_type", "file_q", "file_status", "history", "file_sort"] : []),
          ...(attachmentDraft ? ["attachment_page"] : []),
          ...(attachmentUploadCount > 0 || attachmentBusy ? ["tab"] : [])]} />
      {/* Tabs */}
      <Tabs tabs={TABS} activeKey={activeTab} onChange={setActiveTab} />
      {projectId && ["samples","group-specs"].includes(activeTab) && <ProjectDataScope projectId={projectId} revision={refreshKey}/>}

      {/* Tab content */}
      {activeTab === "overview" && (
        <OverviewTab
          project={projectData}
          loading={loadingProject}
          onNavigate={navigate}
          projectId={projectId}
          assetSetName={query.get("asset_set") || ""}
        />
      )}

      {(activeTab === "assets" || dataProject === projectId) && projectId && <div hidden={activeTab !== "assets"}><ProjectDatasetManager key={projectId} projectId={projectId} revision={refreshKey} active={activeTab === "assets"} onChange={handleRefresh} onDraftChange={setUploadDrafts} onUploadBusyChange={setUploadBusy} onFileDraftChange={setInputFileDraft} /></div>}
      {activeTab === 'attachments' && <section className="data-section">
        <div className="data-section-header"><div><h3>项目附件</h3><p>保存文档、笔记及相关表格；附件不参与分析输入。</p></div>
          <button className="btn btn-primary" onClick={() => setShowAttachmentUpload(true)}><Upload size={16} />上传附件</button></div>
        {projectFiles.status === "error" && <DataReadError title="项目附件暂时无法读取" message={projectFiles.error} onRetry={projectFiles.refetch} retryLabel="重新读取附件" />}
        {(projectFiles.status !== "error" || attachmentSelection.items.length>0) && <AssetTable key={projectId} selection={attachmentSelection} assets={projectFileList} loading={loadingProjectFiles} projectId={projectId} onAssetDeleted={handleRefresh} onDraftChange={setAttachmentDraft} emptyLabel={projectFiles.status === "error" ? "附件列表暂时无法读取，所选文件仍保留。" : "尚未上传项目附件。"} />}
        {projectFiles.status === 'ready' && attachmentPageReady && <Pagination pagination={projectFiles.data.pagination} onPageChange={page => setQuery(previous => { const next = new URLSearchParams(previous); next.set('attachment_page', String(page)); return next; })} />}
        {!showAttachmentUpload && attachmentUploadCount > 0 && <div className="data-draft-warning" role="status"><p>已保留 {attachmentUploadCount} 个未保存附件。</p><div className="data-row-actions"><button className="btn btn-primary" onClick={() => setShowAttachmentUpload(true)}>继续上传附件</button><button className="btn btn-secondary" onClick={() => setDiscardAttachmentUpload(true)}>放弃附件选择</button></div></div>}
        <Sheet open={showAttachmentUpload} keepMounted onClose={() => !attachmentBusy && setShowAttachmentUpload(false)} title="上传项目附件">
          {projectId && <ProjectFileUpload key={`${projectId}:${attachmentUploadRevision}`} projectId={projectId} onBusyChange={setAttachmentBusy} onPendingChange={setAttachmentUploadCount} onSuccess={handleRefresh} />}
        </Sheet>
        <Sheet open={discardAttachmentUpload} title="放弃未保存附件" onClose={() => setDiscardAttachmentUpload(false)}><p>将清除 {attachmentUploadCount} 个未保存附件选择；已保存附件仍在项目中。</p><div className="data-row-actions"><button className="btn btn-primary" onClick={() => {setDiscardAttachmentUpload(false);setShowAttachmentUpload(true);}}>继续上传附件</button><button className="btn btn-danger" disabled={attachmentBusy} onClick={() => {setDiscardAttachmentUpload(false);setAttachmentUploadRevision(value => value + 1);setAttachmentUploadCount(0);}}>确认放弃附件选择</button></div></Sheet>
      </section>}

      {activeTab === "results" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
          <ProjectResultFilters facets={results.status === "ready" ? results.data.facets : undefined}/>
          <div>
            <h4 style={{ margin: "0 0 var(--spacing-sm)", fontSize: "0.85rem", color: "var(--text-secondary)", fontWeight: 600 }}>
              分析结果（{resultPagination?.total ?? projectData?.result_count ?? 0}）
            </h4>
            {results.status !== "error" && <AssetTable
              assets={analysisResults}
              loading={loadingResults}
              emptyLabel={resultDataset || resultType || resultJob || resultUnscoped ? "没有符合当前筛选的分析结果，请调整筛选。" : "尚未生成分析结果。"}
              projectId={projectId}
              onAssetDeleted={handleRefresh}
              showSelect={false}
              showStatus
            />}
          </div>
          {results.status === "error" && <p role="alert" className="data-error">{results.error}<button className="btn btn-secondary" onClick={results.refetch}>重新读取结果</button></p>}
          <Pagination
            pagination={resultPagination}
            onPageChange={setResultPage}
          />
        </div>
      )}

      {activeTab === 'samples' && projectId && <ProjectInputSamples projectId={projectId} revision={refreshKey} onChange={handleRefresh} onDraftChange={setSampleDraft} />}

      {activeTab === "group-specs" && (
        <ProjectGroupSpecs
          onChanged={handleRefresh}
          onDraftChange={setGroupDraft}
          managed
          revision={refreshKey}
          loading={loadingProject}
          projectId={projectId}
        />
      )}

      {activeTab === "settings" && (
        <SettingsTab
          key={projectId}
          onDraftChange={setSettingsDraft}
          project={projectData}
          loading={loadingProject}
          projectId={projectId}
          onSaved={handleRefresh}
        />
      )}

      {/* Edit project sheet */}
      {projectData && (
        <ProjectForm
          open={showEditSheet}
          onDraftChange={setProjectFormDraft}
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

/* ── Overview Tab ───────────────────────────────────────────────────── */

function OverviewTab({
  project,
  loading,
  onNavigate,
  projectId,
  assetSetName,
}: {
  project: Record<string, any> | null;
  loading: boolean;
  onNavigate: (to: string) => void;
  projectId?: string;
  assetSetName: string;
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
      <div className="data-project-metrics"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "var(--spacing-md)",
        }}
      >
        <MetricCard icon={FileText} label="文件总数" value={totalAssets} color="var(--accent)" />
        <MetricCard icon={Boxes} label="输入样本条目" value={project.input_sample_count || 0} color="var(--success)" />
        <MetricCard icon={FlaskConical} label="结果" value={project.result_count || 0} color="var(--warning)" />
        <MetricCard icon={Layers} label="分组方案" value={project.group_spec_count || 0} color="var(--info)" />
      </div>

      {/* Quick actions */}
      <div className="data-project-quick-actions" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--spacing-md)" }}>
        <Card ariaLabel="开始分析" onClick={() => onNavigate(`/analysis/center?project=${encodeURIComponent(projectId || "")}&asset_set=${encodeURIComponent(assetSetName)}`)}>
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
        <Card onClick={() => onNavigate(`/management/projects/${projectId}?tab=assets&import=1&asset_set=${encodeURIComponent(assetSetName)}`)} ariaLabel="上传数据">
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
        <div className="data-project-facts" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-md)", fontSize: "0.85rem" }}>
          <DetailField label="名称" value={project.name} />
          <DetailField label="所属机构" value={project.institution || "—"} />
          <DetailField label="合作类型" value={({ internal: "内部", public: "公开", collaboration: "合作", restricted: "受限", service: "服务" } as Record<string, string>)[project.cooperation_level || ""] || "未填写"} />
          <DetailField label="状态" value={({ active: "进行中", paused: "已暂停", archived: "已归档" } as Record<string, string>)[project.status || "active"] || "未设置"} />
          <DetailField label="创建时间" value={project.created_at ? new Date(project.created_at).toLocaleDateString("zh-CN") : "—"} />
          <DetailField label="更新时间" value={project.updated_at ? new Date(project.updated_at).toLocaleDateString("zh-CN") : "—"} />
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
                  {assetTypeLabels[type] || "其他文件"}
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

/* ── Group Specs Tab ────────────────────────────────────────────────── */

function SettingsTab({
  project,
  loading,
  projectId,
  onSaved,
  onDraftChange,
}: {
  project: Record<string, any> | null;
  loading: boolean;
  projectId?: string;
  onSaved: () => void;
  onDraftChange: (dirty: boolean) => void;
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
  const [baseline, setBaseline] = useState("");
  const draft = JSON.stringify([name.trim(), status, cooperationLevel.trim(), institution.trim(), description.trim()]);
  const dirty = initialized && draft !== baseline;
  useLayoutEffect(() => { onDraftChange(dirty || saving); }, [dirty, saving, onDraftChange]);
  useEffect(() => () => onDraftChange(false), [onDraftChange]);
  if (project && !initialized) {
    setName(project.name || "");
    setStatus(project.status || "active");
    setCooperationLevel(project.cooperation_level || "");
    setInstitution(project.institution || "");
    setDescription(project.description || "");
    setBaseline(JSON.stringify([String(project.name || "").trim(), project.status || "active",
      String(project.cooperation_level || "").trim(), String(project.institution || "").trim(), String(project.description || "").trim()]));
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
      setBaseline(draft);
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
        <div className="data-project-settings-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-md)" }}>
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
            {saving ? "正在保存…" : saveSuccess ? "已保存" : "保存修改"}
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
