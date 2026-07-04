import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type WorkspaceKind = "management" | "analysis";

export interface BreadcrumbSegment {
  label: string;
  path?: string;
}

interface WorkspaceState {
  /** Currently active workspace. */
  workspace: WorkspaceKind;
  /** Switch between management and analysis workspaces. */
  setWorkspace: (ws: WorkspaceKind) => void;
  /** Convenience booleans. */
  isManagement: boolean;
  isAnalysis: boolean;

  /** Currently selected project id, if any. */
  selectedProjectId: string | null;
  /** Currently selected asset id, if any. */
  selectedAssetId: string | null;
  /** Currently selected job id, if any. */
  selectedJobId: string | null;
  /** Whether the hierarchical sidebar is collapsed to icon-only mode. */
  sidebarCollapsed: boolean;
  /** Breadcrumb trail for the current view. */
  breadcrumbs: BreadcrumbSegment[];

  selectProject: (projectId: string | null) => void;
  selectAsset: (assetId: string | null) => void;
  selectJob: (jobId: string | null) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setBreadcrumbs: (segments: BreadcrumbSegment[]) => void;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);

const STORAGE_KEY = "ir-workspace";

function loadWorkspace(): WorkspaceKind {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "management" || stored === "analysis") return stored;
  } catch {
    // localStorage unavailable — use default
  }
  return "management";
}

function saveWorkspace(ws: WorkspaceKind): void {
  try {
    localStorage.setItem(STORAGE_KEY, ws);
  } catch {
    // silently ignore
  }
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspace, setWorkspaceRaw] = useState<WorkspaceKind>(loadWorkspace);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbSegment[]>([]);

  const setWorkspace = useCallback((ws: WorkspaceKind) => {
    setWorkspaceRaw(ws);
    saveWorkspace(ws);
  }, []);

  const isManagement = workspace === "management";
  const isAnalysis = workspace === "analysis";

  const selectProject = useCallback((projectId: string | null) => {
    setSelectedProjectId(projectId);
    if (projectId === null) {
      setSelectedAssetId(null);
      setSelectedJobId(null);
    }
  }, []);

  const selectAsset = useCallback((assetId: string | null) => {
    setSelectedAssetId(assetId);
    if (assetId !== null) setSelectedJobId(null);
  }, []);

  const selectJob = useCallback((jobId: string | null) => {
    setSelectedJobId(jobId);
    if (jobId !== null) setSelectedAssetId(null);
  }, []);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => !prev);
  }, []);

  const value = useMemo<WorkspaceState>(
    () => ({
      workspace,
      setWorkspace,
      isManagement,
      isAnalysis,
      selectedProjectId,
      selectedAssetId,
      selectedJobId,
      sidebarCollapsed,
      breadcrumbs,
      selectProject,
      selectAsset,
      selectJob,
      toggleSidebar,
      setSidebarCollapsed,
      setBreadcrumbs,
    }),
    [
      workspace,
      setWorkspace,
      isManagement,
      isAnalysis,
      selectedProjectId,
      selectedAssetId,
      selectedJobId,
      sidebarCollapsed,
      breadcrumbs,
      selectProject,
      selectAsset,
      selectJob,
      toggleSidebar,
    ],
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceState {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error("useWorkspace must be used within <WorkspaceProvider>");
  }
  return ctx;
}
