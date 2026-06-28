import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  subtitle?: string;
  children?: ReactNode;
};

export function PageHeader({ title, subtitle, children }: PageHeaderProps) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--spacing-lg)",
        flexWrap: "wrap",
      }}
    >
      <div>
        <h2 style={{ margin: 0 }}>{title}</h2>
        {subtitle && (
          <p
            style={{
              margin: "4px 0 0",
              color: "var(--text-secondary)",
              fontSize: "0.875rem",
            }}
          >
            {subtitle}
          </p>
        )}
      </div>
      {children}
    </header>
  );
}
