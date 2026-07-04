import { useState } from "react";
import { FolderOpen, X } from "lucide-react";
import { DirectoryPicker } from "./DirectoryPicker";

type Props = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Enable server-side directory browsing (Linux-compatible). */
  browsable?: boolean;
  browseLabel?: string;
  label?: string;
  hint?: string;
  onCommit?: (value: string) => void;
};

export function PathInput({
  value,
  onChange,
  placeholder = "/data/projects/project-name/pep/",
  disabled,
  browsable = true,
  browseLabel = "Browse",
  label,
  hint,
  onCommit,
}: Props) {
  const [pickerOpen, setPickerOpen] = useState(false);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      {label && (
        <span style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", color: "var(--text-secondary)", fontFamily: "var(--font-family)" }}>
          {label}
        </span>
      )}
      <div style={{ display: "flex", gap: "var(--spacing-sm)" }}>
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            minHeight: "42px",
            padding: "8px 12px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: disabled ? "var(--bg-inset)" : "var(--bg-elevated)",
            transition: "border-color var(--duration-fast), box-shadow var(--duration-fast)",
          }}
          onFocus={(e) => {
            (e.currentTarget as HTMLDivElement).style.borderColor = "var(--accent)";
            (e.currentTarget as HTMLDivElement).style.boxShadow = "0 0 0 3px rgba(0,113,227,0.15)";
          }}
          onBlur={(e) => {
            (e.currentTarget as HTMLDivElement).style.borderColor = "var(--separator)";
            (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
          }}
          tabIndex={0}
        >
          <FolderOpen size={15} style={{ color: "var(--text-tertiary)", flexShrink: 0 }} />
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && onCommit) {
                e.preventDefault();
                onCommit(value);
              }
            }}
            placeholder={placeholder}
            disabled={disabled}
            style={{
              flex: 1,
              border: "none",
              outline: "none",
              background: "transparent",
              color: "var(--text-primary)",
              fontSize: "0.85rem",
              fontFamily: '"SF Mono", "Cascadia Code", "Consolas", monospace',
            }}
          />
          {value && !disabled && (
            <button
              onClick={() => onChange("")}
              style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", padding: "2px", flexShrink: 0 }}
              aria-label="Clear path"
            >
              <X size={14} />
            </button>
          )}
        </div>
        {browsable && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => setPickerOpen(true)}
            className="btn btn-secondary"
            style={{ padding: "8px 16px", flexShrink: 0 }}
          >
            <FolderOpen size={15} />
            {browseLabel}
          </button>
        )}
      </div>
      {hint && (
        <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", marginTop: "2px", fontFamily: "var(--font-family)" }}>
          {hint}
        </span>
      )}

      {/* Server-side directory picker — Linux compatible */}
      {browsable && (
        <DirectoryPicker
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
          onSelect={(path) => {
            onChange(path);
            onCommit?.(path);
          }}
          initialPath={value}
          title="Select Directory"
        />
      )}
    </div>
  );
}
