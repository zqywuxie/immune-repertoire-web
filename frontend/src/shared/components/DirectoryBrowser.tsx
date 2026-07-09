import { useMemo, useCallback, useState } from "react";
import {
  ChevronRight,
  Folder,
  FolderOpen,
  File,
  FileText,
  FileImage,
  FileSpreadsheet,
  FileCode,
  FileArchive,
  Search,
} from "lucide-react";
import type { ProjectAsset } from "../types/domain";
import { useApi } from "../hooks/useApi";
import { listProjectAssets } from "../api/projects";
import { Skeleton } from "./Skeleton";
import styles from "./DirectoryBrowser.module.css";

/* ── Types ── */

export interface DirectoryBrowserProps {
  /** Project id to load assets from. */
  projectId: string;
  /** Called when a file (leaf asset) is clicked. */
  onSelect?: (asset: ProjectAsset) => void;
  /** Currently selected path (storage_uri). */
  selectedPath?: string;
  /** Show a search/filter input at the top. */
  searchable?: boolean;
  /** Placeholder for empty tree. */
  emptyMessage?: string;
}

interface TreeNode {
  name: string;
  path: string;
  isDirectory: boolean;
  children: Map<string, TreeNode>;
  assets: ProjectAsset[];
}

/* ── Helpers ── */

/** Extract path segments from storage_uri or fallback storage_path. */
function parsePathSegments(asset: ProjectAsset): string[] {
  const raw = asset.storage_uri || asset.storage_path || "";
  if (!raw) return [];

  let path = raw;
  const protoEnd = raw.indexOf("://");
  if (protoEnd !== -1) {
    path = raw.slice(protoEnd + 3);
    const firstSlash = path.indexOf("/");
    if (firstSlash !== -1) {
      path = path.slice(firstSlash);
    } else {
      return [];
    }
  }

  path = path.replace(/\\/g, "/");
  return path.split("/").filter(Boolean);
}

/** Build a tree from flat asset list using path segments. */
function buildTree(assets: ProjectAsset[]): TreeNode {
  const root: TreeNode = {
    name: "root",
    path: "",
    isDirectory: true,
    children: new Map(),
    assets: [],
  };

  for (const asset of assets) {
    const segments = parsePathSegments(asset);

    if (segments.length === 0) {
      root.assets.push(asset);
      continue;
    }

    let current = root;
    let currentPath = "";

    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      currentPath = currentPath ? `${currentPath}/${seg}` : seg;
      const isLast = i === segments.length - 1;

      if (isLast) {
        let leaf = current.children.get(seg);
        if (!leaf) {
          leaf = {
            name: seg,
            path: currentPath,
            isDirectory: false,
            children: new Map(),
            assets: [],
          };
          current.children.set(seg, leaf);
        }
        leaf.assets.push(asset);
      } else {
        let dir = current.children.get(seg);
        if (!dir) {
          dir = {
            name: seg,
            path: currentPath,
            isDirectory: true,
            children: new Map(),
            assets: [],
          };
          current.children.set(seg, dir);
        }
        current = dir;
      }
    }
  }

  return root;
}

/** Sort tree nodes: directories first, then alphabetically. */
function sortChildren(node: TreeNode): TreeNode {
  const sorted = new Map(
    [...node.children.entries()].sort((a, b) => {
      const aDir = a[1].isDirectory ? 0 : 1;
      const bDir = b[1].isDirectory ? 0 : 1;
      if (aDir !== bDir) return aDir - bDir;
      return a[0].localeCompare(b[0], undefined, { sensitivity: "base" });
    }),
  );
  for (const [, child] of sorted) {
    sortChildren(child);
  }
  node.children = sorted;
  return node;
}

/** Filter tree nodes by search query (case-insensitive). */
function filterTree(node: TreeNode, query: string): TreeNode | null {
  if (!query) return node;

  const lowerQuery = query.toLowerCase();
  const nameMatch = node.name.toLowerCase().includes(lowerQuery);
  const assetMatch = node.assets.some(
    (a) => (a.original_name || "").toLowerCase().includes(lowerQuery),
  );

  const filteredChildren = new Map<string, TreeNode>();
  for (const [key, child] of node.children) {
    const filtered = filterTree(child, query);
    if (filtered) {
      filteredChildren.set(key, filtered);
    }
  }

  if (nameMatch || assetMatch || filteredChildren.size > 0) {
    return { ...node, children: filteredChildren };
  }

  return null;
}

/** Get icon for a file based on its extension or mime type. */
function getFileIcon(name: string, mimeType?: string | null): typeof File {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";

  if (["png", "jpg", "jpeg", "gif", "svg", "bmp", "webp", "tiff", "tif"].includes(ext)) return FileImage;
  if (mimeType?.startsWith("image/")) return FileImage;

  if (["csv", "tsv", "xls", "xlsx", "ods"].includes(ext)) return FileSpreadsheet;
  if (mimeType?.includes("spreadsheet") || mimeType?.includes("csv")) return FileSpreadsheet;

  if (["py", "r", "rmd", "ipynb", "js", "ts", "json", "yaml", "yml", "txt", "md", "log", "sh"].includes(ext)) return FileCode;

  if (["zip", "tar", "gz", "bz2", "7z", "rar"].includes(ext)) return FileArchive;
  if (mimeType?.includes("zip") || mimeType?.includes("tar") || mimeType?.includes("gzip")) return FileArchive;

  if (mimeType?.startsWith("text/")) return FileText;

  return File;
}

/* ── Component ── */

export function DirectoryBrowser({
  projectId,
  onSelect,
  selectedPath,
  searchable = true,
  emptyMessage = "No assets in this project.",
}: DirectoryBrowserProps) {
  const assetsResult = useApi(
    () => listProjectAssets(projectId).then((res) => res.assets),
    [projectId],
  );

  const assets = assetsResult.status === "ready" ? assetsResult.data : [];
  const loading = assetsResult.status === "loading";
  const error = assetsResult.status === "error" ? assetsResult.error : null;

  const [query, setQuery] = useState("");

  const tree = useMemo(() => {
    const raw = buildTree(assets);
    return sortChildren(raw);
  }, [assets]);

  const filteredTree = useMemo(() => {
    if (!query) return tree;
    return filterTree(tree, query) ?? tree;
  }, [tree, query]);

  const handleSelect = useCallback(
    (asset: ProjectAsset) => {
      onSelect?.(asset);
    },
    [onSelect],
  );

  // Loading skeleton
  if (loading) {
    return (
      <div className={styles.browser}>
        <div className={styles.header}>
          <Folder size={14} />
          Files
        </div>
        <div style={{ padding: "var(--spacing-md)" }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} height="28px" variant="text" />
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className={styles.browser}>
        <div className={styles.header}>
          <Folder size={14} />
          Files
        </div>
        <div className={styles.empty} style={{ color: "var(--danger)" }}>
          Failed to load assets: {error}
        </div>
      </div>
    );
  }

  // Empty state
  if (assets.length === 0) {
    return (
      <div className={styles.browser}>
        <div className={styles.header}>
          <Folder size={14} />
          Files
        </div>
        <div className={styles.empty}>{emptyMessage}</div>
      </div>
    );
  }

  return (
    <div className={styles.browser}>
      <div className={styles.header}>
        <Folder size={14} />
        Files
        <span style={{ marginLeft: "auto", fontWeight: 400, fontSize: "0.7rem" }}>
          {assets.length} item{assets.length !== 1 ? "s" : ""}
        </span>
      </div>

      {searchable && (
        <div className={styles.searchWrap}>
          <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
            <Search
              size={14}
              style={{
                position: "absolute",
                left: "10px",
                color: "var(--text-tertiary)",
                pointerEvents: "none",
              }}
            />
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Filter files..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ paddingLeft: "28px" }}
            />
          </div>
        </div>
      )}

      <div className={styles.tree}>
        {filteredTree && (filteredTree.children.size > 0 || filteredTree.assets.length > 0) ? (
          <TreeNodeView
            node={filteredTree}
            depth={-1}
            selectedPath={selectedPath}
            onSelect={handleSelect}
            defaultExpanded={!query}
          />
        ) : (
          <div className={styles.empty}>
            {query ? "No matching files." : emptyMessage}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Tree Node View ── */

function TreeNodeView({
  node,
  depth,
  selectedPath,
  onSelect,
  defaultExpanded,
}: {
  node: TreeNode;
  depth: number;
  selectedPath?: string;
  onSelect?: (asset: ProjectAsset) => void;
  defaultExpanded: boolean;
}) {
  if (depth === -1) {
    const children = [...node.children.values()];
    return (
      <>
        {children.map((child) => (
          <TreeNodeView
            key={child.path}
            node={child}
            depth={0}
            selectedPath={selectedPath}
            onSelect={onSelect}
            defaultExpanded={defaultExpanded}
          />
        ))}
        {node.assets.map((asset) => (
          <FileRow
            key={asset.id}
            asset={asset}
            depth={0}
            isSelected={asset.storage_uri === selectedPath}
            onClick={() => onSelect?.(asset)}
          />
        ))}
      </>
    );
  }

  if (node.isDirectory) {
    return (
      <DirectoryNode
        node={node}
        depth={depth}
        selectedPath={selectedPath}
        onSelect={onSelect}
        defaultExpanded={defaultExpanded}
      />
    );
  }

  if (node.assets.length === 1) {
    const asset = node.assets[0];
    return (
      <FileRow
        asset={asset}
        depth={depth}
        isSelected={asset.storage_uri === selectedPath}
        onClick={() => onSelect?.(asset)}
      />
    );
  }

  return (
    <>
      {node.assets.map((asset) => (
        <FileRow
          key={asset.id}
          asset={asset}
          depth={depth}
          isSelected={asset.storage_uri === selectedPath}
          onClick={() => onSelect?.(asset)}
        />
      ))}
    </>
  );
}

/* ── Directory Node ── */

function DirectoryNode({
  node,
  depth,
  selectedPath,
  onSelect,
  defaultExpanded,
}: {
  node: TreeNode;
  depth: number;
  selectedPath?: string;
  onSelect?: (asset: ProjectAsset) => void;
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const hasChildren = node.children.size > 0;
  const totalItems = countItems(node);

  const indentCls =
    depth <= 5
      ? (styles as Record<string, string>)[`indent${depth}`]
      : styles.indent5;

  return (
    <div className={styles.node}>
      <button
        className={`${styles.nodeRow} ${indentCls ?? ""}`}
        onClick={() => hasChildren && setExpanded((prev) => !prev)}
        title={node.path}
      >
        <span
          className={`${styles.chevron} ${
            hasChildren
              ? expanded
                ? styles.chevronOpen
                : styles.chevronClosed
              : styles.chevronHidden
          }`}
        >
          <ChevronRight size={14} />
        </span>
        <span className={`${styles.icon} ${styles.iconFolder}`}>
          {expanded ? <FolderOpen size={14} /> : <Folder size={14} />}
        </span>
        <span className={styles.name}>{node.name}</span>
        <span className={styles.meta}>{totalItems}</span>
      </button>

      <div
        className={`${styles.children} ${
          expanded ? styles.childrenOpen : styles.childrenClosed
        }`}
      >
        {[...node.children.values()].map((child) => (
          <TreeNodeView
            key={child.path}
            node={child}
            depth={depth + 1}
            selectedPath={selectedPath}
            onSelect={onSelect}
            defaultExpanded={defaultExpanded}
          />
        ))}
        {node.assets.map((asset) => (
          <FileRow
            key={asset.id}
            asset={asset}
            depth={depth + 1}
            isSelected={asset.storage_uri === selectedPath}
            onClick={() => onSelect?.(asset)}
          />
        ))}
      </div>
    </div>
  );
}

/* ── File Row ── */

function FileRow({
  asset,
  depth,
  isSelected,
  onClick,
}: {
  asset: ProjectAsset;
  depth: number;
  isSelected: boolean;
  onClick?: () => void;
}) {
  const FileIcon = getFileIcon(asset.original_name || "", asset.mime_type);
  const displayName = asset.original_name || asset.id || "unknown";
  const size = formatSize(asset.size);

  const indentCls =
    depth <= 5
      ? (styles as Record<string, string>)[`indent${depth}`]
      : styles.indent5;

  return (
    <button
      className={`${styles.nodeRow} ${indentCls ?? ""} ${
        isSelected ? styles.nodeRowActive : ""
      }`}
      onClick={onClick}
      title={displayName}
    >
      <span className={styles.chevron} />
      <span className={`${styles.icon} ${styles.iconFile}`}>
        <FileIcon size={14} />
      </span>
      <span className={styles.name}>{displayName}</span>
      {size && <span className={styles.meta}>{size}</span>}
    </button>
  );
}

/* ── Helpers ── */

function countItems(node: TreeNode): number {
  let count = node.assets.length;
  for (const child of node.children.values()) {
    count += countItems(child);
  }
  return count;
}

function formatSize(bytes: number): string {
  if (bytes == null || bytes === 0) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let unitIdx = 0;
  let size = bytes;
  while (size >= 1024 && unitIdx < units.length - 1) {
    size /= 1024;
    unitIdx++;
  }
  return `${size.toFixed(unitIdx === 0 ? 0 : 1)} ${units[unitIdx]}`;
}
