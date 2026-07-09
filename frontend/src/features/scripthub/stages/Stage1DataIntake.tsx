import { useState, useEffect, useMemo } from "react";
import {
  FolderOpen,
  Database,
  FileText,
  BarChart3,
  FileSpreadsheet,
  Trash2,
  CheckCircle2,
  Layers,
  ChevronDown,
  ChevronRight,
  FolderTree,
} from "lucide-react";
import { useApi } from "../../../shared/hooks/useApi";
import { listProjects, listProjectAssets, getProject } from "../../../shared/api/projects";
import type { ProjectAsset } from "../../../shared/types/domain";
import { Skeleton } from "../../../shared/components/Skeleton";
import { EmptyState } from "../../../shared/components/EmptyState";
import { Card } from "../../../shared/components/Card";
import { Select } from "../../../shared/components/Select";
import { DirectoryBrowser } from "../../../shared/components/DirectoryBrowser";
import { assetPath, buildAssetSets } from "../../assets/assetSets";

export type BasketKey = "pep" | "profile" | "transcriptome";

export interface Stage1UpdateData {
  projectId: string;
  assetSetName: string;
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
}

interface Stage1DataIntakeProps {
  projectId: string;
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
  onUpdate: (data: Stage1UpdateData) => void;
}

export function Stage1DataIntake({
  projectId,
  pepPaths,
  profilePath,
  transcriptomePath,
  onUpdate,
}: Stage1DataIntakeProps) {
  const [selectedProjectId, setSelectedProjectId] = useState(projectId);
  const [selectedSetName, setSelectedSetName] = useState("");
  const [showBrowser, setShowBrowser] = useState(false);

  const projectsState = useApi(() => listProjects(), []);
  const projects = projectsState.status === "ready" ? projectsState.data.projects : [];
  const projectsError = projectsState.status === "error" ? projectsState.error : null;
  const projectsLoading = projectsState.status === "loading";

  const assetsState = useApi(
    () => selectedProjectId ? listProjectAssets(selectedProjectId, { pageSize: 200 }) : Promise.resolve({ assets: [] as ProjectAsset[] }),
    [selectedProjectId],
  );
  const allAssets = assetsState.status === "ready" ? assetsState.data.assets : [];
  const assetsLoading = assetsState.status === "loading";

  const projectDetailState = useApi(
    () => selectedProjectId ? getProject(selectedProjectId) : Promise.resolve(null as any),
    [selectedProjectId],
  );
  const projectDetail = projectDetailState.status === "ready" ? projectDetailState.data : null;

  const dataSets = useMemo(() => buildAssetSets(allAssets), [allAssets]);

  // Auto-select first data set when detected
  useEffect(() => {
    if (dataSets.length > 0 && pepPaths.length === 0 && !profilePath && !transcriptomePath) {
      const ds = dataSets[0];
      onUpdate({ projectId: selectedProjectId, assetSetName: ds.name, pepPaths: ds.pepPaths, profilePath: ds.profilePath, transcriptomePath: ds.transcriptomePath });
      setSelectedSetName(ds.name);
    }
  }, [selectedProjectId, dataSets.length]);

  useEffect(() => {
    setSelectedProjectId(projectId);
  }, [projectId]);

  const applyDataSet = (name: string) => {
    const ds = dataSets.find((set) => set.name === name);
    if (ds) {
      onUpdate({ projectId: selectedProjectId, assetSetName: ds.name, pepPaths: ds.pepPaths, profilePath: ds.profilePath, transcriptomePath: ds.transcriptomePath });
      setSelectedSetName(ds.name);
    }
  };

  const removePepPath = (p: string) => {
    onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths: pepPaths.filter((x) => x !== p), profilePath, transcriptomePath });
  };

  const handleBrowseSelect = (asset: ProjectAsset) => {
    const path = assetPath(asset);
    const type = (asset.asset_type || "").toLowerCase();
    if (type.includes("profile") || type.includes("datapoint")) {
      onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath: path, transcriptomePath });
    } else if (type.includes("transcriptome") || type.includes("expression")) {
      onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath, transcriptomePath: path });
    } else {
      if (!pepPaths.includes(path)) {
        onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths: [...pepPaths, path], profilePath, transcriptomePath });
      }
    }
  };

  const selectedAny = pepPaths.length > 0 || !!profilePath || !!transcriptomePath;

  if (projectsState.status === "ready" && projects.length === 0) {
    return (
      <EmptyState icon={FolderOpen} title="No projects available"
        description="Create a project from the Dashboard before starting a wizard session."
        action={{ label: "Go to Dashboard", to: "/" }} />
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
      <div>
        <h2 style={{ margin: 0 }}>Stage 1: Data Intake</h2>
        <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          Select a project — PEP / Profile / Transcriptome paths are automatically detected from registered assets.
        </p>
      </div>

      {projectsError && (
        <div style={{ padding: "var(--spacing-md) var(--spacing-lg)", borderRadius: "var(--radius-control)", background: "var(--danger)", color: "#fff", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
          Failed to load projects: {projectsError}
        </div>
      )}

      {/* Project Selector */}
      <Card>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-sm)" }}>
          <span style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", color: "var(--text-secondary)" }}>Project</span>
          {projectsLoading ? <Skeleton height="42px" /> : (
            <Select value={selectedProjectId}
              options={projects.map((p) => ({ value: p.id, label: p.name }))}
              onChange={(id) => {
                setSelectedProjectId(id);
                setSelectedSetName("");
                setShowBrowser(false);
                onUpdate({ projectId: id, assetSetName: "", pepPaths: [], profilePath: "", transcriptomePath: "" });
              }}
              placeholder="Select a project…" />
          )}
        </div>
        {projectDetail && (
          <p style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "var(--spacing-sm)" }}>
            {projectDetail.sample_count || 0} samples · {allAssets.length} registered assets
          </p>
        )}
      </Card>

      {/* Data Set selector */}
      {selectedProjectId && (
        <div style={{ background: "var(--bg-elevated)", borderRadius: "var(--radius-panel)", border: "1px solid var(--separator)", padding: "var(--spacing-lg)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", marginBottom: "var(--spacing-md)" }}>
            <Layers size={16} style={{ color: "var(--text-secondary)" }} />
            <h4 style={{ margin: 0, fontSize: "0.9rem" }}>Analysis Data Sets</h4>
            {assetsLoading ? <Skeleton height="18px" width="60px" variant="text" /> : (
              <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", marginLeft: "auto" }}>
                {dataSets.length} set{dataSets.length !== 1 ? "s" : ""} found
              </span>
            )}
          </div>

          {assetsLoading ? (
            <div style={{ display: "flex", gap: "var(--spacing-md)" }}>
              <Skeleton height="80px" width="180px" /><Skeleton height="80px" width="180px" />
            </div>
          ) : dataSets.length === 0 ? (
            <div style={{ padding: "var(--spacing-lg)", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
              No data sets registered. Use the Assets tab in Project Detail to register PEP/Profile/Transcriptome.
            </div>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)", marginBottom: "var(--spacing-sm)" }}>
              {dataSets.map((ds) => (
                <button key={ds.name} onClick={() => applyDataSet(ds.name)} style={{
                  textAlign: "left", padding: "var(--spacing-md)", borderRadius: "var(--radius-control)",
                  cursor: "pointer", minWidth: "180px",
                  border: selectedSetName === ds.name ? "2px solid var(--accent)" : "1px solid var(--separator)",
                  background: selectedSetName === ds.name ? "rgba(0,113,227,0.06)" : "var(--bg-root)",
                  transition: "border-color var(--duration-fast)",
                }}>
                  <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "6px" }}>
                    {ds.name}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "3px", fontSize: "0.72rem", color: "var(--text-secondary)" }}>
                    <span>PEP: {ds.pepPaths.length} path{ds.pepPaths.length !== 1 ? "s" : ""}</span>
                    <span>Profile: {ds.profilePath ? "✓" : "—"}</span>
                    <span>Transcriptome: {ds.transcriptomePath ? "✓" : "—"}</span>
                  </div>
                  {selectedSetName === ds.name && <CheckCircle2 size={14} style={{ color: "var(--accent)", marginTop: "6px" }} />}
                </button>
              ))}
            </div>
          )}

          {/* Manual override browser */}
          {allAssets.length > 0 && (
            <div>
              <button onClick={() => setShowBrowser(!showBrowser)} style={{
                display: "inline-flex", alignItems: "center", gap: "4px", padding: "4px 0",
                border: "none", background: "transparent", color: "var(--text-secondary)",
                fontSize: "0.78rem", fontWeight: 500, cursor: "pointer",
              }}>
                {showBrowser ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <FolderTree size={14} />
                {showBrowser ? "Hide" : "Browse All Files"} (manual override)
              </button>
              {showBrowser && (
                <div style={{ marginTop: "var(--spacing-sm)", border: "1px solid var(--separator)", borderRadius: "var(--radius-control)", maxHeight: "300px", overflow: "auto" }}>
                  <DirectoryBrowser projectId={selectedProjectId} onSelect={handleBrowseSelect} searchable />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Baskets */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "var(--spacing-lg)" }}>
        {/* PEP */}
        <div style={basketStyle}>
          <div style={basketHeaderStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
              <Database size={18} style={{ color: "var(--accent)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>PEP Paths</span>
            </div>
            <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>{pepPaths.length} path{pepPaths.length !== 1 ? "s" : ""}</span>
          </div>
          {pepPaths.length === 0 ? (
            <div style={{ padding: "var(--spacing-lg)", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
              No PEP paths detected. Register PEP assets in the project or Browse Files above.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              {pepPaths.map((p, i) => (
                <div key={i} style={itemRow}>
                  <FileText size={14} style={{ flexShrink: 0, color: "var(--accent)" }} />
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p}</span>
                  <button onClick={() => removePepPath(p)} style={iconBtn} title="Remove"><Trash2 size={13} style={{ color: "var(--danger)" }} /></button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Profile */}
        <div style={basketStyle}>
          <div style={basketHeaderStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
              <BarChart3 size={18} style={{ color: "var(--success)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>Profile File</span>
              {profilePath && <CheckCircle2 size={14} style={{ color: "var(--success)" }} />}
            </div>
          </div>
          {!profilePath ? (
            <div style={{ padding: "var(--spacing-lg)", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
              No profile file detected.
            </div>
          ) : (
            <div style={itemRow}>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{profilePath}</span>
              <button onClick={() => onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath: "", transcriptomePath })} style={iconBtn} title="Remove"><Trash2 size={13} style={{ color: "var(--danger)" }} /></button>
            </div>
          )}
        </div>

        {/* Transcriptome */}
        <div style={basketStyle}>
          <div style={basketHeaderStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
              <FileSpreadsheet size={18} style={{ color: "var(--warning)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>Transcriptome</span>
              {transcriptomePath && <CheckCircle2 size={14} style={{ color: "var(--warning)" }} />}
            </div>
          </div>
          {!transcriptomePath ? (
            <div style={{ padding: "var(--spacing-lg)", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
              No transcriptome detected.
            </div>
          ) : (
            <div style={itemRow}>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{transcriptomePath}</span>
              <button onClick={() => onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath, transcriptomePath: "" })} style={iconBtn} title="Remove"><Trash2 size={13} style={{ color: "var(--danger)" }} /></button>
            </div>
          )}
        </div>
      </div>

      {/* Confirm */}
      <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--spacing-md)", borderTop: "1px solid var(--separator)" }}>
        <button onClick={() => onUpdate({ projectId: selectedProjectId, assetSetName: selectedSetName, pepPaths, profilePath, transcriptomePath })} style={{
          display: "inline-flex", alignItems: "center", gap: "var(--spacing-sm)", padding: "10px 24px",
          borderRadius: "var(--radius-control)", border: "none", fontWeight: 500, fontSize: "0.9rem",
          background: selectedAny ? "var(--success)" : "var(--bg-inset)",
          color: selectedAny ? "#fff" : "var(--text-tertiary)",
          cursor: selectedAny ? "pointer" : "not-allowed",
        }}>
          <CheckCircle2 size={16} /> Confirm Data
        </button>
      </div>
    </div>
  );
}

/* ── Shared styles ── */

function tag(color: string): React.CSSProperties {
  return {
    display: "inline-flex", alignItems: "center", gap: "4px",
    padding: "3px 10px", borderRadius: "var(--radius-pill)",
    background: `color-mix(in srgb, var(--${color}) 12%, transparent)`,
    color: `var(--${color})`, fontSize: "0.72rem", fontWeight: 500,
  };
}

const basketStyle: React.CSSProperties = {
  background: "var(--bg-elevated)", borderRadius: "var(--radius-panel)",
  border: "1px solid var(--separator)", padding: "var(--spacing-md)",
  display: "flex", flexDirection: "column",
};

const basketHeaderStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "space-between",
  marginBottom: "var(--spacing-sm)",
};

const itemRow: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
  padding: "6px 10px", borderRadius: "var(--radius-control)",
  background: "var(--bg-root)", fontSize: "0.8rem",
};

const iconBtn: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  width: "26px", height: "26px", borderRadius: "var(--radius-control)",
  border: "none", background: "transparent", cursor: "pointer", flexShrink: 0,
};
