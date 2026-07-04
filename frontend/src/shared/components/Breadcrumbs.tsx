import { ChevronRight, Home } from "lucide-react";
import { Link } from "react-router-dom";

/* ── Types ── */

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

export interface BreadcrumbsProps {
  /** Breadcrumb items. Last item is the current page (non-clickable). */
  items: BreadcrumbItem[];
}

/* ── Component ── */

export function Breadcrumbs({ items }: BreadcrumbsProps) {
  const allItems: BreadcrumbItem[] = [{ label: "", to: "/" }, ...items];

  return (
    <nav
      aria-label="Breadcrumb"
      style={{
        display: "flex",
        alignItems: "center",
        gap: "4px",
        fontSize: "0.8rem",
        color: "var(--text-tertiary)",
        flexWrap: "wrap",
        padding: "2px 0",
      }}
    >
      {allItems.map((item, idx) => {
        const isLast = idx === allItems.length - 1;
        const isHome = idx === 0;

        return (
          <span
            key={`${item.label}-${idx}`}
            style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
          >
            {idx > 0 && (
              <ChevronRight size={12} style={{ flexShrink: 0, opacity: 0.5 }} />
            )}
            <Crumb item={item} isLast={isLast} isHome={isHome} />
          </span>
        );
      })}
    </nav>
  );
}

/* ── Internal ── */

function Crumb({
  item,
  isLast,
  isHome,
}: {
  item: BreadcrumbItem;
  isLast: boolean;
  isHome: boolean;
}) {
  const style: React.CSSProperties = {
    color: isLast ? "var(--text-primary)" : "var(--text-secondary)",
    fontWeight: isLast ? 500 : 400,
    textDecoration: "none",
    cursor: isLast ? "default" : "pointer",
    whiteSpace: "nowrap",
    display: "inline-flex",
    alignItems: "center",
    gap: "2px",
    borderRadius: "4px",
    padding: "1px 4px",
    transition: "background var(--duration-fast)",
    maxWidth: "200px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    background: "transparent",
    border: "none",
    fontFamily: "inherit",
    fontSize: "inherit",
  };

  // Home icon — clickable to root
  if (isHome) {
    if (isLast && !item.to) {
      return (
        <span style={{ ...style, color: "var(--text-tertiary)" }} title="Home">
          <Home size={13} />
        </span>
      );
    }
    return (
      <Link to={item.to ?? "/"} style={style} title="Home">
        <Home size={13} />
      </Link>
    );
  }

  // Last item — non-clickable
  if (isLast) {
    return (
      <span style={style} title={item.label}>
        {item.label}
      </span>
    );
  }

  // Clickable intermediate
  if (item.to) {
    return (
      <Link
        to={item.to}
        style={style}
        title={item.label}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLAnchorElement).style.background =
            "var(--bg-inset)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLAnchorElement).style.background = "transparent";
        }}
      >
        {item.label}
      </Link>
    );
  }

  // Has no to — render as span
  return (
    <span style={{ ...style, cursor: "default" }} title={item.label}>
      {item.label}
    </span>
  );
}
