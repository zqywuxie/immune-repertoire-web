import { Select } from "./Select";
import { useMemo, useState } from "react";
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
import { Pagination } from "./Pagination";
import styles from "./DirectoryBrowser.module.css";

/* ── Types ── */

export interface DirectoryBrowserProps {
  /** Project id to load assets from. */
  projectId: string;
  assetSet?: string;
  inputsOnly?: boolean;
  assetType?: string;
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
  projectId, assetSet, inputsOnly = false, assetType,
  onSelect, selectedPath, searchable = true,
  emptyMessage = "此范围暂无数据文件。",
}: DirectoryBrowserProps) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [history, setHistory] = useState(false);
  const [inputType,setInputType]=useState("");
  const selectedType=assetType || inputType || undefined;
  const [treeView, setTreeView] = useState(false);
  const assetsResult = useApi(() => listProjectAssets(projectId, {
    assetSet, inputsOnly, assetType:selectedType, search: query.trim(), page, pageSize: 50,
    includeSuperseded: history,
  }), [projectId, assetSet, inputsOnly, selectedType, query, page, history]);
  const assets = assetsResult.status === "ready" ? assetsResult.data.assets : [];
  const tree = useMemo(() => sortChildren(buildTree(assets)), [assets]);
  return <div className={styles.browser} aria-label="文件浏览与选择">
    <div className={styles.header}><Folder size={14} />文件
      {assetSet && <span> · 数据集：{assetSet}</span>}
      {assetsResult.status === "ready" && <span style={{marginLeft:"auto",fontWeight:400}}>共 {assetsResult.data.pagination?.total ?? assets.length} 项</span>}
    </div>
    {inputsOnly && !assetType && <div style={{padding:8}}><Select ariaLabel="浏览文件类型" value={inputType} options={[{value:"",label:"全部输入类型"},{value:"pep",label:"克隆序列表"},{value:"profile",label:"样本指标表"},{value:"transcriptome",label:"转录组"},{value:"deconvolution",label:"免疫细胞浸润"}]} onChange={value=>{setInputType(value);setPage(1);}}/></div>}
    {searchable && <div className={styles.searchWrap}>
      <div style={{position:"relative",display:"flex",alignItems:"center"}}>
        <Search size={14} style={{position:"absolute",left:10,color:"var(--text-tertiary)",pointerEvents:"none"}}/>
        <input type="search" aria-label="搜索文件名" className={styles.searchInput} placeholder="搜索文件名…" value={query}
          onChange={event=>{setQuery(event.target.value);setPage(1);}} style={{paddingLeft:28}}/>
      </div>
      {query && <button className="btn btn-secondary" onClick={()=>{setQuery("");setPage(1);}}>清除搜索</button>}
    </div>}
    <button className="btn btn-secondary" style={{margin:8,alignSelf:"flex-start"}} aria-pressed={treeView} onClick={()=>setTreeView(previous=>!previous)}>{treeView ? "返回文件列表" : "按目录浏览"}</button>
    {inputsOnly && <label style={{display:"flex",gap:8,padding:12,fontSize:13}}><input type="checkbox" checked={history}
      onChange={event=>{setHistory(event.target.checked);setPage(1);}}/>显示历史版本</label>}
    <div className={styles.tree}>
      {assetsResult.status === "loading" || assetsResult.status === "idle" ? <div role="status" style={{padding:12}}>正在读取文件…<Skeleton height="28px"/></div>
        : assetsResult.status === "error" ? <div className={styles.empty} role="alert">文件读取失败：{assetsResult.error}<button className="btn btn-secondary" onClick={assetsResult.refetch}>重新读取</button></div>
        : !assets.length ? <div className={styles.empty}>{query ? "没有匹配的文件。" : emptyMessage}</div>
        : treeView ? <TreeNodeView key={`${projectId}:${assetSet}:${assetType}:${query}:${page}:${history}`} node={tree} depth={-1} selectedPath={selectedPath} onSelect={onSelect} defaultExpanded/>
        : assets.map(asset=><FileRow key={asset.id} asset={asset} depth={0} isSelected={(asset.storage_uri || asset.storage_path)===selectedPath} onClick={()=>onSelect?.(asset)}/>)}
    </div>
    {assetsResult.status === "ready" && assetsResult.data.pagination && <div style={{padding:12}}><Pagination pagination={assetsResult.data.pagination} onPageChange={setPage}/></div>}
  </div>;
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
            isSelected={(asset.storage_uri || asset.storage_path) === selectedPath}
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
        isSelected={(asset.storage_uri || asset.storage_path) === selectedPath}
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
          isSelected={(asset.storage_uri || asset.storage_path) === selectedPath}
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
            isSelected={(asset.storage_uri || asset.storage_path) === selectedPath}
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
  const displayName = asset.original_name || asset.id || "未命名文件";
  const size = formatSize(asset.size);
  const state = asset.metadata?.superseded ? "历史版本" : "当前文件";
  const version = String(asset.metadata?.content_version || asset.id);

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
      aria-label={`${displayName} · ${state} · 版本 ${version.slice(0,8)}`}
      title={`${displayName} · ${state} · 版本 ${version} · ${asset.uploaded_at || "上传时间未记录"}`}
    >
      <span className={styles.chevron} />
      <span className={`${styles.icon} ${styles.iconFile}`}>
        <FileIcon size={14} />
      </span>
      <span className={styles.name}><span style={{display:"block",overflow:"hidden",textOverflow:"ellipsis"}}>{displayName}</span><small style={{display:"block",fontSize:11,color:"var(--text-secondary)",overflow:"hidden",textOverflow:"ellipsis"}}>{state} · {asset.uploaded_at?.replace("T", " ").slice(0,16) || "时间未记录"} · {version.slice(0,8)}</small></span>
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
