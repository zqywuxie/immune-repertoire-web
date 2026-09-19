import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
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
  Clock,
  User,
  LogOut,
  type LucideIcon,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useWorkspace } from "../context/WorkspaceContext";
import styles from "./Sidebar.module.css";
import { analysisCategories, analysisTools, toolPath } from "../../features/analysis/tools";

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
    label: "数据管理",
    items: [
      { key: "workbench", label: "项目概览", to: "/management", icon: LayoutDashboard },
      { key: "projects", label: "项目管理", to: "/management/projects", icon: FolderTree },
      { key: "samples", label: "样本管理", to: "/management/samples", icon: Database },
      { key: "mgmt-settings", label: "工作台设置", to: "/management/settings", icon: Settings },
    ],
  },
];

const ANALYSIS_SECTIONS: SidebarSection[] = [
  {
    key: "analysis-nav",
    label: "分析工具",
    items: [
      { key: "data-analysis", label: "分析中心", to: "/analysis/center", icon: BarChart3 },
      { key: "background-tasks", label: "任务与结果", to: "/analysis/script-hub/jobs", icon: Clock },
    ],
  },
  ...analysisCategories.map(category => ({key:category.id,label:category.title,items:analysisTools.filter(tool=>tool.category===category.id).map(tool=>({key:tool.id,label:tool.title,to:toolPath(tool),icon:FlaskConical}))})),
  {
    key: "analysis-experimental",
    label: "偏好设置",
    items: [
      { key: "analysis-settings", label: "分析设置", to: "/analysis/settings", icon: Settings },
    ],
  },
];

/* ── Component ── */

export function Sidebar() {
  const {user, logout}=useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { setWorkspace, sidebarCollapsed, toggleSidebar } =
    useWorkspace();

  const { pathname, search } = useLocation();
  const projectQuery = new URLSearchParams(search).get("project");
  const navigate = useNavigate();
  const isManagement = !pathname.startsWith("/analysis");
  function switchWorkspace(ws: "analysis" | "management") {
    setWorkspace(ws);
    navigate(ws === "analysis" ? `/analysis/center${projectQuery ? `?project=${encodeURIComponent(projectQuery)}` : ""}` : "/management");
  }
  const sections = isManagement ? MANAGEMENT_SECTIONS : ANALYSIS_SECTIONS;

  return (
    <aside
      className={`${styles.sidebar} ${sidebarCollapsed ? styles.sidebarCollapsed : styles.sidebarExpanded}`}
      aria-label="工作台导航"
      style={{ background: "var(--bg-elevated)", borderRight: "1px solid var(--separator)" }}
    >
      <Link to="/" className={styles.homeLink} title="返回内部工作台">{sidebarCollapsed ? "免" : "免疫组库 · 分析平台"}</Link>
      {/* Workspace switch tabs */}
      {!sidebarCollapsed && (
        <div
          style={{
            display: "flex",
            padding: "var(--spacing-sm) var(--spacing-md)",
            gap: "4px",
            borderBottom: "1px solid var(--separator)",
            flexShrink: 0,
          }}
        >
          <WorkspaceTab
            active={isManagement}
            label="数据管理"
            onClick={() => switchWorkspace("management")}
          />
          <WorkspaceTab
            active={!isManagement}
            label="分析工作台"
            onClick={() => switchWorkspace("analysis")}
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
            borderBottom: "1px solid var(--separator)",
            flexShrink: 0,
          }}
        >
          <WorkspaceDot
            active={isManagement}
            label="数据管理"
            onClick={() => switchWorkspace("management")}
          />
          <WorkspaceDot
            active={!isManagement}
            label="分析工作台"
            onClick={() => switchWorkspace("analysis")}
          />
        </div>
      )}

      {/* Header with toggle */}
      <div
        className={`${styles.header} ${sidebarCollapsed ? styles.headerCollapsed : ""}`}
        style={{
          borderBottom: "1px solid var(--separator)",
          color: "var(--text-secondary)",
        }}
      >
        {!sidebarCollapsed && (
          <span
            className={styles.projectTitle}
            style={{ color: "var(--text-primary)" }}
          >
            {isManagement ? "数据管理" : "分析工作台"}
          </span>
        )}
        {sidebarCollapsed && (
          <span style={{ color: "var(--text-secondary)", fontSize: "0.65rem", fontWeight: 600 }}>
            {isManagement ? "MG" : "AN"}
          </span>
        )}
        <button
          className={styles.toggleBtn}
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? "展开导航" : "收起导航"}
          title={sidebarCollapsed ? "展开导航" : "收起导航"}
          style={{ color: "var(--text-secondary)" }}
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

    {user?.auth_mode !== "internal" && <div className={styles.footer} style={{ display: "grid", gap: 12, padding: 16 }}>
      <Link to="/account" title="账号信息" aria-label="账号信息"><User size={18}/>{!sidebarCollapsed && <span>{user?.username}</span>}</Link>
      <button className="btn btn-secondary" disabled={busy} aria-label="退出登录" title="退出登录" onClick={async () => {
        setBusy(true); setError("");
        try { await logout(); navigate("/login", { replace: true }); }
        catch { setError("退出失败，请重试。"); }
        finally { setBusy(false); }
      }}><LogOut size={16}/>{!sidebarCollapsed && (busy ? "正在退出…" : "退出登录")}</button>
      {error && <p role="alert">{error}</p>}
    </div>}
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
        background: active ? "var(--bg-inset)" : "transparent",
        color: active ? "var(--accent)" : "var(--text-secondary)",
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
        background: active ? "var(--text-primary)" : "var(--separator)",
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
  const { pathname, search } = useLocation();
  const projectQuery = new URLSearchParams(search).get("project");
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
        style={{ color: "var(--text-secondary)" }}
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
                color: "var(--text-tertiary)",
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
              to={item.to.startsWith("/analysis") && projectQuery ? `${item.to}?project=${encodeURIComponent(projectQuery)}` : item.to}
              aria-label={item.label}
              aria-current={isActive ? "page" : undefined}
              className={`${styles.navItem} ${collapsed ? styles.navItemCollapsed : ""} ${isActive ? styles.navItemActive : ""}`}
              title={collapsed ? item.label : undefined}
              style={{
                color: isActive
                  ? "var(--accent)"
                  : collapsed
                    ? "var(--text-secondary)"
                    : "var(--text-secondary)",
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
