import { assetDownloadUrl, assetPreviewUrl } from "../../shared/api/projects";
import type { ProjectAsset } from "../../shared/types/domain";
import { SkeletonRow } from "../../shared/components/Skeleton";

function formatSize(size: number): string {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}

export function AssetTable({
  assets,
  loading,
  emptyLabel = "No assets found.",
}: {
  assets: ProjectAsset[];
  loading: boolean;
  emptyLabel?: string;
}) {
  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        overflow: "hidden",
      }}
    >
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr
            style={{
              background: "var(--bg-root)",
              borderBottom: "1px solid var(--separator)",
            }}
          >
            {["Name", "Type", "Size", "Uploaded", "Actions"].map((h) => (
              <th
                key={h}
                scope="col"
                style={{
                  textAlign: "left",
                  padding: "12px 16px",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  color: "var(--text-secondary)",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <SkeletonRow columns={5} />
          ) : assets.length === 0 ? (
            <tr>
              <td
                colSpan={5}
                style={{
                  padding: "var(--spacing-3xl) var(--spacing-lg)",
                  textAlign: "center",
                  color: "var(--text-tertiary)",
                }}
              >
                {emptyLabel}
              </td>
            </tr>
          ) : (
            assets.map((asset) => (
              <tr
                key={asset.id}
                style={{ borderBottom: "1px solid var(--separator)" }}
              >
                <td
                  style={{
                    padding: "12px 16px",
                    maxWidth: "240px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {asset.original_name}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  <span
                    style={{
                      padding: "2px 8px",
                      borderRadius: "var(--radius-pill)",
                      background: "var(--bg-inset)",
                      fontSize: "0.75rem",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {asset.asset_type}
                  </span>
                </td>
                <td style={{ padding: "12px 16px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  {formatSize(asset.size)}
                </td>
                <td style={{ padding: "12px 16px", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  {formatDate(asset.uploaded_at)}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  <div style={{ display: "flex", gap: "var(--spacing-xs)" }}>
                    <AssetLink href={assetPreviewUrl(asset.id)} label="Preview" />
                    <AssetLink href={assetDownloadUrl(asset.id)} label="Download" />
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function AssetLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      style={{
        padding: "6px 12px",
        borderRadius: "var(--radius-control)",
        border: "1px solid var(--separator)",
        color: "var(--accent)",
        fontSize: "0.8rem",
        fontWeight: 500,
        textDecoration: "none",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </a>
  );
}
