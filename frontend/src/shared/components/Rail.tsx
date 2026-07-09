import { NavLink } from "react-router-dom";
import { User, Settings } from "lucide-react";
import type { LucideIcon } from "lucide-react";

type RailLink = {
  to: string;
  icon: LucideIcon;
  label: string;
};

type Props = {
  links: RailLink[];
  /** If provided, rendered at the bottom of the rail (auth indicator, settings, etc.). */
  footer?: React.ReactNode;
};

export function Rail({ links, footer }: Props) {
  return (
    <nav
      style={{
        width: "var(--rail-width)",
        minHeight: "100vh",
        background: "#1d1d1f",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "var(--spacing-xl) 0",
        gap: "var(--spacing-md)",
        flexShrink: 0,
      }}
      aria-label="Main navigation"
    >
      <div
        style={{
          width: "40px",
          height: "40px",
          display: "grid",
          placeItems: "center",
          color: "var(--accent)",
          fontWeight: 800,
          fontSize: "1.1rem",
          letterSpacing: "0.04em",
          marginBottom: "var(--spacing-sm)",
        }}
      >
        IR
      </div>

      <div
        style={{
          width: "36px",
          height: "1px",
          background: "rgba(255,255,255,0.12)",
          marginBottom: "var(--spacing-sm)",
        }}
      />

      {links.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          aria-label={label}
          aria-current="page"
          title={label}
          style={({ isActive }) => ({
            width: "44px",
            height: "44px",
            display: "grid",
            placeItems: "center",
            borderRadius: "var(--radius-control)",
            color: isActive ? "#ffffff" : "#aeaeb2",
            background: isActive ? "var(--accent)" : "transparent",
            transition: `background var(--duration-fast), color var(--duration-fast)`,
          })}
        >
          <Icon size={20} />
        </NavLink>
      ))}

      {/* Spacer pushes footer to bottom */}
      <div style={{ flex: 1 }} />

      {footer ?? <DefaultFooter />}
    </nav>
  );
}

/** Default footer shown when no custom footer is provided. */
function DefaultFooter() {
  const authMode = import.meta.env.VITE_AUTH_MODE || import.meta.env.DEV ? "dev" : "token";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "4px",
        paddingBottom: "var(--spacing-md)",
      }}
    >
      <div
        title={`Auth mode: ${authMode}`}
        style={{
          width: "36px",
          height: "36px",
          display: "grid",
          placeItems: "center",
          borderRadius: "50%",
          background: "rgba(255,255,255,0.08)",
          color: "#aeaeb2",
          cursor: "default",
        }}
      >
        <User size={18} />
      </div>
      <span
        style={{
          fontSize: "0.6rem",
          color: "rgba(255,255,255,0.3)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
        }}
      >
        {authMode}
      </span>
    </div>
  );
}
