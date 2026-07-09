export function ProgressBar({
  value,
  max = 100,
}: {
  value: number;
  max?: number;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));

  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      style={{
        width: "100%",
        height: "6px",
        borderRadius: "3px",
        background: "var(--bg-inset)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          height: "100%",
          width: `${pct}%`,
          borderRadius: "3px",
          background:
            pct >= 100 ? "var(--success)" : "var(--accent)",
          transition: "width 400ms ease-out",
        }}
      />
    </div>
  );
}
