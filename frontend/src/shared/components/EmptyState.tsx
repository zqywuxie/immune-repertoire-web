import type { LucideIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";

type EmptyStateProps = {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; to: string };
};

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  const navigate = useNavigate();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "var(--spacing-md)",
        padding: "var(--spacing-5xl) var(--spacing-xl)",
        textAlign: "center",
      }}
    >
      <Icon
        size={48}
        strokeWidth={1}
        style={{ color: "var(--text-tertiary)" }}
      />
      <div>
        <h3 style={{ margin: 0 }}>{title}</h3>
        {description && (
          <p
            style={{
              margin: "6px 0 0",
              color: "var(--text-secondary)",
              fontSize: "0.875rem",
            }}
          >
            {description}
          </p>
        )}
      </div>
      {action && (
        <button
          onClick={() => navigate(action.to)}
          style={{
            padding: "10px 20px",
            borderRadius: "var(--radius-control)",
            background: "var(--accent)",
            color: "#ffffff",
            fontWeight: 500,
            transition: `background var(--duration-fast)`,
          }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
