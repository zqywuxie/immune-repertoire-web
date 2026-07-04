type Props = {
  projectId: string;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
};

export function ImageSelectionForm({ projectId, value, onChange }: Props) {
  const setField = (k: string, v: unknown) => onChange({ ...value, [k]: v });

  const selections: Array<{ image_id: string; slide_position?: number }> =
    Array.isArray(value.image_selections)
      ? (value.image_selections as Array<{
          image_id: string;
          slide_position?: number;
        }>)
      : [];

  const addSelection = () => {
    setField("image_selections", [
      ...selections,
      { image_id: "", slide_position: selections.length + 1 },
    ]);
  };

  const updateSelection = (idx: number, field: string, val: string | number) => {
    const next = selections.map((s, i) => (i === idx ? { ...s, [field]: val } : s));
    setField("image_selections", next);
  };

  const removeSelection = (idx: number) => {
    setField(
      "image_selections",
      selections.filter((_, i) => i !== idx)
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span
          style={{
            fontSize: "0.75rem",
            fontWeight: 600,
            textTransform: "uppercase",
            color: "var(--text-secondary)",
          }}
        >
          Image Selections
        </span>
        <button
          type="button"
          onClick={addSelection}
          style={{
            padding: "4px 12px",
            borderRadius: "var(--radius-pill)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--accent)",
            fontSize: "0.78rem",
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          + Add Image
        </button>
      </div>

      {selections.length === 0 && (
        <p
          style={{
            color: "var(--text-tertiary)",
            fontSize: "0.82rem",
            textAlign: "center",
            padding: "var(--spacing-md)",
          }}
        >
          No images selected. Click "+ Add Image" to add.
        </p>
      )}

      {selections.map((sel, idx) => (
        <div
          key={idx}
          style={{
            display: "flex",
            gap: "var(--spacing-sm)",
            alignItems: "end",
            padding: "var(--spacing-sm)",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: "var(--bg-root)",
          }}
        >
          <label style={fieldLabelStyle}>
            Image ID
            <input
              type="text"
              value={sel.image_id}
              onChange={(e) => updateSelection(idx, "image_id", e.target.value)}
              placeholder="asset-id"
              style={inputStyle}
            />
          </label>
          <label style={fieldLabelStyle}>
            Position
            <input
              type="number"
              value={sel.slide_position ?? ""}
              onChange={(e) =>
                updateSelection(idx, "slide_position", parseInt(e.target.value) || 0)
              }
              placeholder="1"
              min={1}
              style={{ ...inputStyle, width: "70px" }}
            />
          </label>
          <button
            type="button"
            onClick={() => removeSelection(idx)}
            style={{
              padding: "6px 8px",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--separator)",
              background: "var(--bg-elevated)",
              color: "var(--danger)",
              fontSize: "0.75rem",
              cursor: "pointer",
              marginBottom: "2px",
            }}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

const fieldLabelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "3px",
  fontSize: "0.7rem",
  fontWeight: 600,
  color: "var(--text-secondary)",
  flex: 1,
};

const inputStyle: React.CSSProperties = {
  minHeight: "34px",
  padding: "5px 8px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.82rem",
};
