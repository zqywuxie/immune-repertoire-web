import type { LucideIcon } from "lucide-react";

type MetricCardProps = {
  icon: LucideIcon;
  label: string;
  value: number;
  color?: string;
};

export function MetricCard({
  icon: Icon,
  label,
  value,
  color = "var(--accent)",
}: MetricCardProps) {
  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-card)",
        padding: "var(--spacing-xl)",
        boxShadow: "var(--shadow-sm)",
        border: "1px solid var(--separator)",
        display: "flex",
        alignItems: "flex-start",
        gap: "var(--spacing-lg)",
      }}
    >
      <div
        style={{
          width: "44px",
          height: "44px",
          borderRadius: "var(--radius-control)",
          background: `${color}12`,
          color: color,
          display: "grid",
          placeItems: "center",
          flexShrink: 0,
        }}
      >
        <Icon size={22} />
      </div>
      <div>
        <div
          style={{
            fontSize: "2rem",
            fontWeight: 700,
            lineHeight: 1,
            color: "var(--text-primary)",
          }}
        >
          {value.toLocaleString()}
        </div>
        <div
          style={{
            color: "var(--text-secondary)",
            fontSize: "0.875rem",
            marginTop: "4px",
          }}
        >
          {label}
        </div>
      </div>
    </div>
  );
}
