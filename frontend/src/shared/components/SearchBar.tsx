import { Search } from "lucide-react";

type Props = {
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
  onClear?: () => void;
};

export function SearchBar({ placeholder = "Search…", value, onChange, onClear }: Props) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", width: "100%", maxWidth: "400px" }}>
      <div
        style={{
          flex: 1, display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
          padding: "7px 12px", borderRadius: "var(--radius-pill)",
          border: "1px solid var(--separator)", background: "var(--bg-elevated)",
        }}
      >
        <Search size={16} style={{ color: "var(--text-tertiary)", flexShrink: 0 }} />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          style={{
            flex: 1, border: "none", outline: "none", background: "transparent",
            color: "var(--text-primary)", fontSize: "0.85rem",
          }}
          aria-label={placeholder}
        />
      </div>
      {value && onClear && (
        <button
          onClick={() => { onChange(""); onClear(); }}
          style={{
            padding: "4px 10px", borderRadius: "var(--radius-pill)", border: "1px solid var(--separator)",
            background: "var(--bg-elevated)", color: "var(--text-secondary)",
            fontSize: "0.75rem", cursor: "pointer",
          }}
        >
          Clear
        </button>
      )}
    </div>
  );
}
