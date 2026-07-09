import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Database,
  FolderTree,
  FlaskConical,
  LayoutDashboard,
  Settings,
  BarChart3,
  ScrollText,
  Clock,
  Calculator,
  FileText,
  Presentation,
  Beaker,
  User,
  LogOut,
  type LucideIcon,
} from "lucide-react";
import { useWorkspace } from "../context/WorkspaceContext";
import styles from "./Sidebar.module.css";

/* ── Types ── */

export interface SidebarNavItem {
  key: string;
  label: string;
  to: string;
  icon: LucideIcon;
  badge?: string | number;
}

export interface SidebarSection {
  key: string;
  label: string;
  icon?: LucideIcon;
  items: SidebarNavItem[];
}

/* ── Navigation config ── */

const MANAGEMENT_SECTIONS: SidebarSection[] = [
  {
    key: "management-nav",
    label: "Data Management",
    items: [
      { key: "workbench", label: "Data Workbench", to: "/management", icon: LayoutDashboard },
      { key: "projects", label: "Project Library", to: "/management/projects", icon: FolderTree },
      { key: "samples", label: "Sample Library", to: "/management/samples", icon: Database },
      { key: "mgmt-settings", label: "Management Settings", to: "/management/settings", icon: Settings },
    ],
  },
];

const ANALYSIS_SECTIONS: SidebarSection[] = [
  {
    key: "analysis-nav",
    label: "Analysis Tools",
    items: [
      { key: "data-analysis", label: "Data Analysis", to: "/analysis", icon: BarChart3 },
      { key: "script-hub", label: "ScriptHub", to: "/analysis/script-hub", icon: ScrollText },
      { key: "background-tasks", label: "Background Tasks", to: "/analysis/script-hub/jobs", icon: Clock },
      { key: "statistical", label: "Statistical Tests", to: "/analysis/statistical", icon: Calculator },
      { key: "pdf-extractor", label: "PDF Extraction", to: "/analysis/pdf-extractor", icon: FileText },
      { key: "ppt-tools", label: "PPT Tools", to: "/analysis/ppt-tools", icon: Presentation },
    ],
  },
  {
    key: "analysis-experimental",
    label: "Experimental",
    items: [
      { key: "analysis-settings", label: "Analysis Settings", to: "/analysis/settings", icon: Settings },
    ],
  },
];

/* ── Component ── */

export function Sidebar() {
  const { workspace, setWorkspace, sidebarCollapsed, toggleSidebar, isManagement } =
    useWorkspace();

  const sections = isManagement ? MANAGEMENT_SECTIONS : ANALYSIS_SECTIONS;

  return (
    <aside
      className={`${styles.sidebar} ${sidebarCollapsed ? styles.sidebarCollapsed : styles.sidebarExpanded}`}
      aria-label="Navigation sidebar"
      style={{ background: "#1d1d1f", borderRight: "1px solid rgba(255,255,255,0.08)" }}
    >
      {/* Workspace switch tabs */}
      {!sidebarCollapsed && (
        <div
          style={{
            display: "flex",
            padding: "var(--spacing-sm) var(--spacing-md)",
            gap: "4px",
            borderBottom: "1px solid rgba(255,255,255,0.08)",
            flexShrink: 0,
          }}
        >
          <WorkspaceTab
            active={isManagement}
            label="Management"
            onClick={() => setWorkspace("management")}
          />
          <WorkspaceTab
            active={!isManagement}
            label="Analysis"
            onClick={() => setWorkspace("analysis")}
          />
        </div>
      )}

      {/* Collapse button when sidebar is collapsed */}
      {sidebarCollapsed && (
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            padding: "var(--spacing-sm) 0",
            borderBottom: "1px solid rgba(255,255,255,0.08)",
            flexShrink: 0,
          }}
        >
          <WorkspaceDot
            active={isManagement}
            label="Management"
            onClick={() => setWorkspace("management")}
          />
          <WorkspaceDot
            active={!isManagement}
            label="Analysis"
            onClick={() => setWorkspace("analysis")}
          />
        </div>
      )}

      {/* Header with toggle */}
      <div
        className={`${styles.header} ${sidebarCollapsed ? styles.headerCollapsed : ""}`}
        style={{
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          color: "rgba(255,255,255,0.7)",
        }}
      >
        {!sidebarCollapsed && (
          <span
            className={styles.projectTitle}
            style={{ color: "rgba(255,255,255,0.9)" }}
          >
            {isManagement ? "Data Management" : "Analysis Platform"}
          </span>
        )}
        {sidebarCollapsed && (
          <span style={{ color: "rgba(255,255,255,0.5)", fontSize: "0.65rem", fontWeight: 600 }}>
            {isManagement ? "MG" : "AN"}
          </span>
        )}
        <button
          className={styles.toggleBtn}
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          style={{ color: "rgba(255,255,255,0.5)" }}
        >
          {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* Navigation sections */}
      <nav className={styles.scrollArea}>
        {sections.map((section) => (
          <SidebarSectionView
            key={section.key}
            section={section}
            collapsed={sidebarCollapsed}
          />
        ))}
      </nav>

      {/* User / auth footer */}
      <div
        className={`${styles.footer} ${sidebarCollapsed ? styles.footerCollapsed : ""}`}
        style={{
          borderTop: "1px solid rgba(255,255,255,0.08)",
          padding: sidebarCollapsed ? "var(--spacing-sm)" : "var(--spacing-md)",
        }}
      >
        {sidebarCollapsed ? (
          <User size={18} style={{ color: "rgba(255,255,255,0.5)" }} />
        ) : (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              width: "100%",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
              <User size={16} style={{ color: "rgba(255,255,255,0.6)" }} />
              <span style={{ fontSize: "0.78rem", color: "rgba(255,255,255,0.7)", fontWeight: 500 }}>
                Guest
              </span>
            </div>
            <button
              title="Sign out"
              style={{
                background: "none",
                border: "none",
                color: "rgba(255,255,255,0.4)",
                cursor: "pointer",
                padding: "2px",
                borderRadius: "4px",
                display: "flex",
                alignItems: "center",
              }}
              onClick={() => {
                fetch("/api/auth/logout", { method: "POST", credentials: "include" }).then(() => {
                  window.location.href = "/login";
                });
              }}
            >
              <LogOut size={14} />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

/* ── Workspace Tab ── */

function WorkspaceTab({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        padding: "6px 10px",
        borderRadius: "var(--radius-control)",
        border: "none",
        background: active ? "rgba(255,255,255,0.12)" : "transparent",
        color: active ? "rgba(255,255,255,0.95)" : "rgba(255,255,255,0.45)",
        fontSize: "0.75rem",
        fontWeight: active ? 600 : 400,
        cursor: "pointer",
        transition: "background var(--duration-fast), color var(--duration-fast)",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </button>
  );
}

function WorkspaceDot({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      style={{
        width: "10px",
        height: "10px",
        borderRadius: "50%",
        border: "none",
        background: active ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.25)",
        cursor: "pointer",
        margin: "0 4px",
        transition: "background var(--duration-fast)",
      }}
    />
  );
}

/* ── Section View ── */

function SidebarSectionView({
  section,
  collapsed,
}: {
  section: SidebarSection;
  collapsed: boolean;
}) {
  const [open, setOpen] = useState(true);
  const { pathname } = useLocation();
  const Icon = section.icon;

  function handleHeaderClick() {
    if (!collapsed) setOpen((prev) => !prev);
  }

  const isOpen = collapsed || open;

  return (
    <div className={styles.section}>
      <button
        className={`${styles.sectionHeader} ${collapsed ? styles.sectionHeaderCollapsed : ""}`}
        onClick={handleHeaderClick}
        aria-expanded={isOpen}
        title={collapsed ? section.label : undefined}
        style={{ color: "rgba(255,255,255,0.5)" }}
      >
        {Icon && <Icon size={collapsed ? 18 : 14} />}
        {!collapsed && (
          <>
            <span className={styles.sectionLabel}>{section.label}</span>
            <ChevronDown
              size={12}
              style={{
                marginLeft: "auto",
                transform: open ? "rotate(0deg)" : "rotate(-90deg)",
                transition: "transform var(--duration-fast)",
                flexShrink: 0,
                color: "rgba(255,255,255,0.3)",
              }}
            />
          </>
        )}
      </button>

      <div
        className={`${styles.sectionContent} ${isOpen ? styles.sectionContentOpen : styles.sectionContentClosed}`}
      >
        {section.items.map((item) => {
          const isActive =
            pathname === item.to ||
            (item.to === "/management/projects" && pathname.startsWith("/management/projects/"));
          return (
            <Link
              key={item.key}
              to={item.to}
              className={`${styles.navItem} ${collapsed ? styles.navItemCollapsed : ""} ${isActive ? styles.navItemActive : ""}`}
              title={collapsed ? item.label : undefined}
              style={{
                color: isActive
                  ? "var(--accent)"
                  : collapsed
                    ? "rgba(255,255,255,0.45)"
                    : "rgba(255,255,255,0.65)",
              }}
            >
              <item.icon size={collapsed ? 18 : 14} className={styles.navItemIcon} />
              {!collapsed && (
                <>
                  <span className={styles.navItemLabel}>{item.label}</span>
                  {item.badge != null && (
                    <span className={styles.navItemBadge}>{item.badge}</span>
                  )}
                </>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

/* ── Re-exports ── */

export { styles as sidebarStyles };
