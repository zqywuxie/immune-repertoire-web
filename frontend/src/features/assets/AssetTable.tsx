import { useState, useMemo } from "react";
import { Download, Trash2, CheckSquare, Square, X, Pencil, Save, Tag } from "lucide-react";
import { assetDownloadUrl, assetPreviewUrl } from "../../shared/api/projects";
import type { ProjectAsset } from "../../shared/types/domain";
import { SkeletonRow } from "../../shared/components/Skeleton";
import { Sheet } from "../../shared/components/Sheet";
import { Select } from "../../shared/components/Select";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { getAssetSetName } from "./assetSets";

type AssetWithLinks = ProjectAsset & {
  preview_url?: string | null;
  download_url?: string | null;
};

function formatSize(size: number): string {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function assetName(asset: ProjectAsset): string {
  const meta = asset.metadata || {};
  if (asset.asset_type === "pep") {
    return asset.storage_path || String(meta.storage_path || meta.path || asset.original_name || asset.id);
  }
  return asset.original_name || asset.storage_path || asset.id;
}

function assetStatus(asset: ProjectAsset): string {
  const meta = asset.metadata || {};
  const raw =
    (asset as ProjectAsset & { status?: unknown }).status ||
    meta.status ||
    meta.job_status ||
    meta.analysis_status ||
    meta.state;
  return typeof raw === "string" && raw.trim() ? raw.trim() : "completed";
}

function previewHref(asset: ProjectAsset): string {
  return String((asset as AssetWithLinks).preview_url || "").trim() || assetPreviewUrl(asset.id);
}

function downloadHref(asset: ProjectAsset): string {
  return String((asset as AssetWithLinks).download_url || "").trim() || assetDownloadUrl(asset.id);
}

type Props = {
  assets: ProjectAsset[];
  loading: boolean;
  emptyLabel?: string;
  projectId?: string;
  onAssetDeleted?: () => void;
  showSelect?: boolean;
  showGroup?: boolean;
  showStatus?: boolean;
};

export function AssetTable({
  assets,
  loading,
  emptyLabel = "No assets found.",
  projectId,
  onAssetDeleted,
  showSelect = true,
  showGroup = false,
  showStatus = false,
}: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState<Set<string>>(new Set());
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [groupFilter, setGroupFilter] = useState("");
  const [editAsset, setEditAsset] = useState<ProjectAsset | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [savingLabel, setSavingLabel] = useState(false);

  // Extract unique groups from assets
  const groups = useMemo(() => {
    const set = new Set<string>();
    for (const a of assets) {
      const g = getAssetSetName(a);
      if (g) set.add(g);
    }
    return [...set].sort();
  }, [assets]);

  // Filter assets by selected group
  const filteredAssets = useMemo(() => {
    if (!groupFilter) return assets;
    return assets.filter((a) => getAssetSetName(a) === groupFilter);
  }, [assets, groupFilter]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };
  const selectAll = () => {
    if (selected.size === filteredAssets.length) setSelected(new Set());
    else setSelected(new Set(filteredAssets.map((a) => a.id)));
  };

  const handleSaveLabel = async () => {
    if (!editAsset) return;
    setSavingLabel(true);
    try {
      const url = projectId
        ? `${API_BASE}/api/projects/${projectId}/assets/${editAsset.id}`
        : `${API_BASE}/api/assets/${editAsset.id}`;
      const setName = editLabel.trim() || "Set1";
      const meta = { ...((editAsset as any).metadata || {}), asset_set: setName, group_label: setName };
      const r = await fetch(url, { method: "PATCH", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metadata_json: meta }),
      });
      if (!r.ok) throw new Error("Save failed");
      setEditAsset(null);
      onAssetDeleted?.();
    } catch { /* ignore */ }
    finally { setSavingLabel(false); }
  };

  const handleSingleDelete = async (assetId: string) => {
    setDeleting((prev) => new Set(prev).add(assetId));
    setDeleteError("");
    try {
      const url = projectId
        ? `${API_BASE}/api/projects/${projectId}/assets/${assetId}`
        : `${API_BASE}/api/assets/${assetId}`;
      const r = await fetch(url, { method: "DELETE", credentials: "include" });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error((e as { detail?: string }).detail || (e as { message?: string }).message || "Delete failed");
      }
      setConfirmDelete(null);
      onAssetDeleted?.();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting((prev) => { const n = new Set(prev); n.delete(assetId); return n; });
    }
  };

  const handleBulkDelete = async () => {
    setBulkDeleting(true);
    setDeleteError("");
    let count = 0;
    for (const id of selected) {
      try {
        const url = projectId
          ? `${API_BASE}/api/projects/${projectId}/assets/${id}`
          : `${API_BASE}/api/assets/${id}`;
        const r = await fetch(url, { method: "DELETE", credentials: "include" });
        if (r.ok) count++;
      } catch { /* continue */ }
    }
    setBulkDeleting(false);
    setSelected(new Set());
    onAssetDeleted?.();
    setDeleteError(count > 0 ? `${count} asset(s) deleted.` : "Delete failed.");
  };

  const handleBulkDownload = () => {
    for (const id of selected) {
      const asset = filteredAssets.find((item) => item.id === id);
      window.open(asset ? downloadHref(asset) : assetDownloadUrl(id), "_blank");
    }
  };

  const bulkSize = selected.size;
  const columnCount = (showSelect ? 1 : 0) + (showGroup ? 1 : 0) + 5 + (showStatus ? 1 : 0);
  const headers = ["Name", "Type", ...(showStatus ? ["Status"] : []), "Size", "Uploaded", "Actions"];

  return (
    <div style={{ background: "var(--bg-elevated)", borderRadius: "var(--radius-panel)", border: "1px solid var(--separator)", overflow: "hidden" }}>
      {/* Bulk action bar */}
      {bulkSize > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)", padding: "var(--spacing-sm) var(--spacing-lg)", background: "rgba(0,113,227,0.06)", borderBottom: "1px solid var(--separator)" }}>
          <button onClick={selectAll} style={{ border: "none", background: "transparent", cursor: "pointer", display: "flex", alignItems: "center", gap: "4px", fontSize: "0.78rem", color: "var(--text-secondary)" }}>
            <X size={14} /> Deselect All
          </button>
          <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--accent)" }}>{bulkSize} selected</span>
          <button onClick={handleBulkDownload} className="btn btn-secondary" style={{ marginLeft: "auto", padding: "6px 14px", fontSize: "0.78rem" }}>
            <Download size={14} /> Download ({bulkSize})
          </button>
          <button onClick={handleBulkDelete} disabled={bulkDeleting} className="btn btn-danger" style={{ padding: "6px 14px", fontSize: "0.78rem" }}>
            <Trash2 size={14} /> {bulkDeleting ? "Deleting…" : `Delete (${bulkSize})`}
          </button>
        </div>
      )}
      {/* Group filter bar */}
      {showGroup && groups.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", padding: "var(--spacing-sm) var(--spacing-lg)", borderBottom: "1px solid var(--separator)", background: "var(--bg-root)" }}>
          <Tag size={14} style={{ color: "var(--text-tertiary)" }} />
          <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)", fontWeight: 500 }}>Set:</span>
          <Select
            value={groupFilter}
            options={[{ value: "", label: "All Sets" }, ...groups.map((g) => ({ value: g, label: g }))]}
            onChange={setGroupFilter}
            placeholder="All Sets"
          />
        </div>
      )}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "var(--bg-root)", borderBottom: "1px solid var(--separator)" }}>
            {showSelect && (
              <th style={{ width: "42px", padding: "12px 8px 12px 16px" }}>
                <button onClick={selectAll} style={{ border: "none", background: "none", cursor: "pointer", padding: 0, color: "var(--text-tertiary)" }}>
                  {selected.size === filteredAssets.length && filteredAssets.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
                </button>
              </th>
            )}
            {showGroup && (
              <th scope="col" style={{ textAlign: "left", padding: "12px 8px", fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)" }}>
                Set
              </th>
            )}
            {headers.map((h) => (
              <th key={h} scope="col" style={{ textAlign: "left", padding: "12px 16px", fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <SkeletonRow columns={columnCount} />
          ) : filteredAssets.length === 0 ? (
            <tr>
              <td colSpan={columnCount} style={{ padding: "var(--spacing-3xl) var(--spacing-lg)", textAlign: "center", color: "var(--text-tertiary)" }}>
                {groupFilter ? `No assets in set "${groupFilter}".` : emptyLabel}
              </td>
            </tr>
          ) : (
            filteredAssets.map((asset) => (
              <tr key={asset.id} style={{ borderBottom: "1px solid var(--separator)", background: selected.has(asset.id) ? "rgba(0,113,227,0.04)" : "transparent" }}>
                {showSelect && (
                  <td style={{ padding: "12px 8px 12px 16px" }}>
                    <button onClick={() => toggleSelect(asset.id)} style={{ border: "none", background: "none", cursor: "pointer", padding: 0, color: "var(--text-tertiary)" }}>
                      {selected.has(asset.id) ? <CheckSquare size={16} style={{ color: "var(--accent)" }} /> : <Square size={16} />}
                    </button>
                  </td>
                )}
                {showGroup && (
                  <td style={{ padding: "12px 8px" }}>
                    <span style={{ padding: "2px 8px", borderRadius: "var(--radius-pill)", background: "rgba(0,113,227,0.08)", fontSize: "0.72rem", color: "var(--accent)", fontWeight: 500 }}>
                      {getAssetSetName(asset)}
                    </span>
                  </td>
                )}
                <td
                  title={assetName(asset)}
                  style={{
                    padding: "12px 16px",
                    maxWidth: asset.asset_type === "pep" ? "420px" : "240px",
                    overflow: "hidden",
                    textOverflow: asset.asset_type === "pep" ? "clip" : "ellipsis",
                    whiteSpace: asset.asset_type === "pep" ? "normal" : "nowrap",
                    wordBreak: asset.asset_type === "pep" ? "break-all" : "normal",
                    fontFamily: asset.asset_type === "pep" ? '"SF Mono", "Cascadia Code", "Consolas", monospace' : undefined,
                    fontSize: asset.asset_type === "pep" ? "0.78rem" : undefined,
                    lineHeight: 1.45,
                  }}
                >
                  {assetName(asset)}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  <span style={{ padding: "2px 8px", borderRadius: "var(--radius-pill)", background: "var(--bg-inset)", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    {asset.asset_type}
                  </span>
                </td>
                {showStatus && (
                  <td style={{ padding: "12px 16px" }}>
                    <StatusBadge status={assetStatus(asset)} />
                  </td>
                )}
                <td style={{ padding: "12px 16px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  {formatSize(asset.size)}
                </td>
                <td style={{ padding: "12px 16px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  {formatDate(asset.uploaded_at)}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  <div style={{ display: "flex", gap: "var(--spacing-xs)" }}>
                    <AssetLink href={previewHref(asset)} label="Preview" />
                    <AssetLink href={downloadHref(asset)} label="Download" />
                    <button
                      onClick={() => { setEditAsset(asset); setEditLabel(getAssetSetName(asset)); }}
                      disabled={deleting.has(asset.id)}
                      style={{ padding: "6px 10px", borderRadius: "var(--radius-control)", border: "1px solid var(--separator)", background: "transparent", color: "var(--text-secondary)", fontSize: "0.8rem", cursor: "pointer", whiteSpace: "nowrap" }}
                    ><Pencil size={12} /></button>
                    <button
                      onClick={() => { setConfirmDelete(asset.id); setDeleteError(""); }}
                      disabled={deleting.has(asset.id)}
                      style={{ padding: "6px 12px", borderRadius: "var(--radius-control)", border: "1px solid var(--danger)", background: "transparent", color: "var(--danger)", fontSize: "0.8rem", fontWeight: 500, cursor: "pointer", whiteSpace: "nowrap" }}
                    >Del</button>
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {/* Edit asset Sheet */}
      <Sheet open={!!editAsset} onClose={() => setEditAsset(null)} title="Edit Asset">
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
          <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            <strong>{editAsset?.original_name}</strong> · {editAsset?.asset_type}
          </div>
          <label className="field-label">
            Asset Set
            <input type="text" value={editLabel} onChange={(e) => setEditLabel(e.target.value)} className="input" placeholder="e.g. Set1, baseline-run" />
          </label>
          <div style={{ display: "flex", gap: "var(--spacing-sm)", justifyContent: "flex-end" }}>
            <button onClick={() => setEditAsset(null)} disabled={savingLabel} style={{ padding: "8px 16px", borderRadius: "var(--radius-control)", border: "1px solid var(--separator)", background: "var(--bg-elevated)", color: "var(--text-primary)", cursor: "pointer" }}>Cancel</button>
            <button onClick={handleSaveLabel} disabled={savingLabel} className="btn btn-primary"><Save size={14} /> {savingLabel ? "Saving…" : "Save"}</button>
          </div>
        </div>
      </Sheet>

      {/* Delete confirmation Sheet */}
      <Sheet open={!!confirmDelete} onClose={() => setConfirmDelete(null)} title="Delete Asset">
        <p style={{ fontSize: "0.9rem", color: "var(--text-primary)" }}>
          Are you sure you want to delete this asset? This action cannot be undone.
        </p>
        {deleteError && <p style={{ fontSize: "0.85rem", color: "var(--danger)" }}>{deleteError}</p>}
        <div style={{ display: "flex", gap: "var(--spacing-sm)", justifyContent: "flex-end" }}>
          <button onClick={() => setConfirmDelete(null)} disabled={bulkDeleting || deleting.size > 0} style={{ padding: "8px 16px", borderRadius: "var(--radius-control)", border: "1px solid var(--separator)", background: "var(--bg-elevated)", color: "var(--text-primary)", cursor: "pointer" }}>
            Cancel
          </button>
          <button onClick={() => confirmDelete && handleSingleDelete(confirmDelete)} disabled={deleting.has(confirmDelete || "")} style={{ padding: "8px 16px", borderRadius: "var(--radius-control)", background: "var(--danger)", color: "#fff", fontWeight: 500, border: "none", cursor: "pointer" }}>
            {deleting.has(confirmDelete || "") ? "Deleting…" : "Delete"}
          </button>
        </div>
      </Sheet>
    </div>
  );
}

function AssetLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" style={{
      padding: "6px 12px", borderRadius: "var(--radius-control)",
      border: "1px solid var(--separator)", color: "var(--accent)",
      fontSize: "0.8rem", fontWeight: 500, textDecoration: "none", whiteSpace: "nowrap",
    }}>
      {label}
    </a>
  );
}
