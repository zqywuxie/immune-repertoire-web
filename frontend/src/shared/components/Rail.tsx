import { NavLink } from "react-router-dom";
import type { LucideIcon } from "lucide-react";

type RailLink = {
  to: string;
  icon: LucideIcon;
  label: string;
};

export function Rail({ links }: { links: RailLink[] }) {
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
    </nav>
  );
}
