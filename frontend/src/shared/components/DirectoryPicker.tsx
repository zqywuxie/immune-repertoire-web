import { useState, useCallback, useEffect } from "react";
import { Folder, FolderOpen, ChevronRight, Home, RefreshCw, X } from "lucide-react";
import { useApi } from "../hooks/useApi";
import { listDirectories, type DirectoryItem } from "../api/directories";
import { Skeleton } from "./Skeleton";

type Props = {
  open: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
  /** Optional initial path to start from. */
  initialPath?: string;
  /** Title for the picker. */
  title?: string;
};

export function DirectoryPicker({ open, onClose, onSelect, initialPath, title = "Browse Directory" }: Props) {
  const [currentPath, setCurrentPath] = useState(initialPath || "");
  const [pathDraft, setPathDraft] = useState(initialPath || "");
  const [breadcrumb, setBreadcrumb] = useState<string[]>([]);

  const dirsState = useApi(
    () => listDirectories(currentPath || undefined),
    [currentPath],
  );

  const items: DirectoryItem[] = dirsState.status === "ready" ? dirsState.data.directories : [];
  const roots: string[] = dirsState.status === "ready" ? (dirsState.data.roots || []) : [];
  const parentPath: string | null = dirsState.status === "ready" ? dirsState.data.parent_path : null;
  const loading = dirsState.status === "loading";
  const error = dirsState.status === "error" ? dirsState.error : null;

  // Navigate into a directory
  const navigateTo = useCallback((path: string) => {
    setBreadcrumb((prev) => [...prev, currentPath].filter(Boolean));
    setCurrentPath(path);
    setPathDraft(path);
  }, [currentPath]);

  // Navigate up one level
  const navigateUp = useCallback(() => {
    if (parentPath !== null && parentPath !== undefined) {
      setBreadcrumb((prev) => prev.slice(0, -1));
      setCurrentPath(parentPath);
      setPathDraft(parentPath);
    }
  }, [parentPath]);

  // Go to root level
  const goToRoot = useCallback(() => {
    setBreadcrumb([]);
    setCurrentPath("");
    setPathDraft("");
  }, []);

  const commitTypedPath = useCallback(() => {
    const nextPath = pathDraft.trim();
    setBreadcrumb([]);
    setCurrentPath(nextPath);
    setPathDraft(nextPath);
  }, [pathDraft]);

  useEffect(() => {
    if (!open) return;
    const nextPath = initialPath || "";
    setCurrentPath(nextPath);
    setPathDraft(nextPath);
    setBreadcrumb([]);
  }, [initialPath, open]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.2)",
          zIndex: 100, backdropFilter: "blur(2px)",
        }}
      />
      {/* Modal */}
      <div
        style={{
          position: "fixed", inset: 0, zIndex: 101,
          display: "flex", alignItems: "center", justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            pointerEvents: "auto",
            background: "var(--bg-elevated)",
            borderRadius: "var(--radius-card)",
            boxShadow: "var(--shadow-lg)",
            width: "min(560px, 90vw)", maxHeight: "70vh",
            display: "flex", flexDirection: "column",
          }}
        >
          {/* Header */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "var(--spacing-lg) var(--spacing-xl)",
            borderBottom: "1px solid var(--separator)",
          }}>
            <h4 style={{ margin: 0, fontSize: "0.95rem" }}>{title}</h4>
            <button onClick={onClose} style={{ width: "28px", height: "28px", borderRadius: "50%", display: "grid", placeItems: "center", color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer" }}>
              <X size={16} />
            </button>
          </div>

          {/* Navigation bar */}
          <div style={{
            display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
            padding: "var(--spacing-sm) var(--spacing-lg)",
            borderBottom: "1px solid var(--separator)",
            background: "var(--bg-root)",
          }}>
            <button onClick={goToRoot} title="Root" style={navBtnStyle}>
              <Home size={14} />
            </button>
            <button onClick={navigateUp} disabled={!parentPath && !currentPath} title="Up" style={navBtnStyle}>
              <ChevronRight size={14} style={{ transform: "rotate(-90deg)" }} />
            </button>
            <input
              type="text"
              value={pathDraft}
              onChange={(e) => setPathDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  commitTypedPath();
                }
              }}
              placeholder="/path/to/directory"
              aria-label="Directory path"
              style={{
              flex: 1, padding: "4px 8px", borderRadius: "6px",
              border: "1px solid var(--separator)",
              background: "var(--bg-elevated)", fontSize: "0.78rem",
              color: "var(--text-secondary)", fontFamily: '"SF Mono", "Cascadia Code", monospace',
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              outline: "none",
            }}
            />
            <button onClick={commitTypedPath} title="Go to typed path" style={navBtnStyle}>
              Go
            </button>
            <button onClick={() => dirsState.refetch?.()} title="Refresh" style={navBtnStyle}>
              <RefreshCw size={14} />
            </button>
          </div>

          {/* Content */}
          <div style={{ flex: 1, overflow: "auto", padding: "var(--spacing-sm)" }}>
            {loading ? (
              <div style={{ padding: "var(--spacing-md)" }}>
                {[1, 2, 3, 4, 5, 6].map((i) => <Skeleton key={i} height="32px" variant="text" />)}
              </div>
            ) : error ? (
              <div style={{ padding: "var(--spacing-xl)", textAlign: "center", color: "var(--danger)", fontSize: "0.85rem" }}>
                Failed to load: {error}
              </div>
            ) : items.length === 0 ? (
              <div style={{ padding: "var(--spacing-xl)", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
                {currentPath ? "No subdirectories found." : "Select a directory root to browse."}
              </div>
            ) : (
              items.map((item) => (
                <button
                  key={item.path}
                  onClick={() => navigateTo(item.path)}
                  style={{
                    display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
                    width: "100%", textAlign: "left", padding: "10px 12px",
                    borderRadius: "var(--radius-control)", border: "none",
                    background: "transparent", cursor: "pointer",
                    color: "var(--text-primary)", fontSize: "0.85rem",
                    transition: "background var(--duration-fast)",
                  }}
                  onMouseEnter={(e) => { (e.target as HTMLButtonElement).style.background = "var(--bg-inset)"; }}
                  onMouseLeave={(e) => { (e.target as HTMLButtonElement).style.background = "transparent"; }}
                  onDoubleClick={() => onSelect(item.path)}
                >
                  <span style={{ color: "var(--accent)", flexShrink: 0 }}>
                    {item.has_children ? <FolderOpen size={16} /> : <Folder size={16} />}
                  </span>
                  <span style={{ flex: 1 }}>{item.name}</span>
                  <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
                    {item.has_children ? "" : "—"}
                  </span>
                </button>
              ))
            )}
          </div>

          {/* Footer */}
          <div style={{
            display: "flex", justifyContent: "flex-end", gap: "var(--spacing-sm)",
            padding: "var(--spacing-md) var(--spacing-lg)",
            borderTop: "1px solid var(--separator)",
          }}>
            <button onClick={onClose} className="btn btn-secondary" style={{ fontSize: "0.82rem" }}>Cancel</button>
            <button
              onClick={() => { onSelect(pathDraft.trim() || currentPath); onClose(); }}
              className="btn btn-primary"
              style={{ fontSize: "0.82rem" }}
              disabled={!(pathDraft.trim() || currentPath)}
            >
              Select This Directory
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

const navBtnStyle: React.CSSProperties = {
  width: "30px", height: "30px", borderRadius: "6px",
  display: "grid", placeItems: "center",
  background: "transparent", border: "none",
  color: "var(--text-secondary)", cursor: "pointer",
  flexShrink: 0,
};
