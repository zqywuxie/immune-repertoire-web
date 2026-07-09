import type { GroupSpec } from "../../../shared/api/groupSpecs";

type Props = {
  projectId: string;
  groupSpecs: GroupSpec[];
  loadingSpecs: boolean;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
};

const STAT_METRICS = [
  "diversity",
  "clonality",
  "richness",
  "evenness",
  "cdr3_length",
  "aa_frequency",
  "v_usage",
  "j_usage",
  "vj_pairing",
];

export function MultiSelectForm({
  projectId,
  groupSpecs,
  loadingSpecs,
  value,
  onChange,
}: Props) {
  const setField = (k: string, v: unknown) => onChange({ ...value, [k]: v });

  const selectedSpecs: string[] = Array.isArray(value.group_spec_ids)
    ? (value.group_spec_ids as string[])
    : [];
  const selectedMetrics: string[] = Array.isArray(value.metrics)
    ? (value.metrics as string[])
    : [];
  const selectedSamples: string[] = Array.isArray(value.sample_ids)
    ? (value.sample_ids as string[])
    : [];
  const selectedProjects: string[] = Array.isArray(value.project_ids)
    ? (value.project_ids as string[])
    : [];

  const toggleItem = (list: string[], key: string, field: string) => {
    const next = list.includes(key)
      ? list.filter((k) => k !== key)
      : [...list, key];
    setField(field, next);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
      {/* Group specs multi-select */}
      <MultiSelectSection
        title="Group Specs"
        items={groupSpecs.map((s) => ({ key: s.id, label: s.name }))}
        selected={selectedSpecs}
        onToggle={(key) => toggleItem(selectedSpecs, key, "group_spec_ids")}
        loading={loadingSpecs}
        placeholder="Select group specs…"
      />

      {/* Metrics multi-select (for statistical modules) */}
      <MultiSelectSection
        title="Metrics"
        items={STAT_METRICS.map((m) => ({
          key: m,
          label: m.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        }))}
        selected={selectedMetrics}
        onToggle={(key) => toggleItem(selectedMetrics, key, "metrics")}
      />

      {/* Sample IDs text input (for statistical.analyze-direct) */}
      <label
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "4px",
          fontSize: "0.75rem",
          fontWeight: 600,
          textTransform: "uppercase",
          color: "var(--text-secondary)",
        }}
      >
        Sample IDs
        <input
          type="text"
          placeholder="Comma-separated sample IDs"
          value={(value.sample_ids as string[])?.join(", ") || ""}
          onChange={(e) =>
            setField(
              "sample_ids",
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            )
          }
          style={inputStyle}
        />
      </label>

      {/* Project IDs text input (for analysis.batch) */}
      <label
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "4px",
          fontSize: "0.75rem",
          fontWeight: 600,
          textTransform: "uppercase",
          color: "var(--text-secondary)",
        }}
      >
        Project IDs
        <input
          type="text"
          placeholder="Comma-separated project IDs"
          value={(value.project_ids as string[])?.join(", ") || ""}
          onChange={(e) =>
            setField(
              "project_ids",
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            )
          }
          style={inputStyle}
        />
      </label>
    </div>
  );
}

function MultiSelectSection({
  title,
  items,
  selected,
  onToggle,
  loading,
  placeholder = "None selected",
}: {
  title: string;
  items: { key: string; label: string }[];
  selected: string[];
  onToggle: (key: string) => void;
  loading?: boolean;
  placeholder?: string;
}) {
  if (!items.length && !loading) return null;

  return (
    <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
      <legend
        style={{
          fontSize: "0.75rem",
          fontWeight: 600,
          textTransform: "uppercase",
          color: "var(--text-secondary)",
          marginBottom: "var(--spacing-sm)",
        }}
      >
        {title}
        {selected.length > 0 && ` (${selected.length})`}
      </legend>
      {loading ? (
        <small style={{ color: "var(--text-tertiary)", fontSize: "0.72rem" }}>
          Loading…
        </small>
      ) : (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "var(--spacing-xs)",
          }}
        >
          {items.map((item) => {
            const isSelected = selected.includes(item.key);
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => onToggle(item.key)}
                style={{
                  padding: "4px 10px",
                  borderRadius: "var(--radius-pill)",
                  border: "1px solid var(--separator)",
                  background: isSelected ? "var(--accent)" : "var(--bg-elevated)",
                  color: isSelected ? "#fff" : "var(--text-primary)",
                  fontSize: "0.78rem",
                  fontWeight: isSelected ? 600 : 400,
                  cursor: "pointer",
                  transition: "background var(--duration-fast), color var(--duration-fast)",
                }}
              >
                {isSelected ? "✓ " : ""}
                {item.label}
              </button>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}

const inputStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
};
