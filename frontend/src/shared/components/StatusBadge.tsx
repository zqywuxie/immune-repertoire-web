const STATUS_COLORS: Record<string, string> = {
  queued: "#0071e3",
  running: "#ff9500",
  completed: "#34c759",
  failed: "#ff3b30",
  cancelled: "#aeaeb2",
};

export function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] || "#aeaeb2";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "4px 10px",
        borderRadius: "var(--radius-pill)",
        fontSize: "0.75rem",
        fontWeight: 600,
        textTransform: "capitalize",
        background: `${color}18`,
        color: color,
        border: `1px solid ${color}30`,
      }}
    >
      <span
        style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
        }}
      />
      {status}
    </span>
  );
}
