import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { BarChart3, Clock, ChevronLeft, ChevronRight, LogOut, User } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useWorkspace } from "../context/WorkspaceContext";
import styles from "./Sidebar.module.css";

export function Sidebar() {
  const { user, logout } = useAuth();
  const { sidebarCollapsed: collapsed, toggleSidebar } = useWorkspace();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const project = new URLSearchParams(search).get("project");
  const suffix = project ? `?project=${encodeURIComponent(project)}` : "";
  const inResults = pathname.startsWith("/analysis/script-hub/jobs");
  return <aside aria-label="平台导航" className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : styles.sidebarExpanded}`}>
    <Link className={styles.homeLink} to="/analysis/center">{collapsed ? "免" : "免疫组库分析平台"}</Link>
    <div className={styles.header}>
      {!collapsed && <span>科研工作台</span>}
      <button className={styles.toggleBtn} onClick={toggleSidebar} aria-label={collapsed ? "展开导航" : "收起导航"}>{collapsed ? <ChevronRight size={18}/> : <ChevronLeft size={18}/>}</button>
    </div>
    <nav className={styles.scrollArea}>
      {[{ to: "/analysis/center", label: "分析中心", icon: BarChart3, active: !inResults && pathname !== "/account" },
        { to: "/analysis/script-hub/jobs", label: "任务与结果", icon: Clock, active: inResults }].map(item =>
        <Link key={item.to} to={item.to + suffix} title={item.label} aria-label={item.label} aria-current={item.active ? "page" : undefined}
          className={`${styles.navItem} ${collapsed ? styles.navItemCollapsed : ""} ${item.active ? styles.navItemActive : ""}`}>
          <item.icon size={18}/>{!collapsed && <span>{item.label}</span>}
        </Link>)}
    </nav>
    {user?.auth_mode !== "internal" && <div className={styles.footer} style={{ display: "grid", gap: 12, padding: 16 }}>
      <Link to="/account" title="账号信息" aria-label="账号信息"><User size={18}/>{!collapsed && <span>{user?.username}</span>}</Link>
      <button className="btn btn-secondary" disabled={busy} aria-label="退出登录" title="退出登录" onClick={async () => {
        setBusy(true); setError("");
        try { await logout(); navigate("/login", { replace: true }); }
        catch { setError("退出失败，请重试。"); }
        finally { setBusy(false); }
      }}><LogOut size={16}/>{!collapsed && (busy ? "正在退出…" : "退出登录")}</button>
      {error && <p role="alert">{error}</p>}
    </div>}
  </aside>;
}
export { styles as sidebarStyles };
