import { Routes, Route, Outlet, Navigate } from "react-router-dom";
import { Suspense, lazy } from "react";
import { ErrorBoundary } from "../shared/components/ErrorBoundary";
import { Skeleton } from "../shared/components/Skeleton";
import { Sidebar } from "../shared/components/Sidebar";
import { WorkspaceProvider } from "../shared/context/WorkspaceContext";
import { AuthProvider, useAuth } from "../shared/context/AuthContext";
import { ToastProvider } from "../shared/hooks/useToast";
import { ProtectedRoute } from "../shared/components/ProtectedRoute";
import "./App.css";
import { AnalysisDataProvider } from "../features/analysis/AnalysisDataContext";

// ── Lazy-loaded pages ──────────────────────────────────────────────────

// Management workspace
const ProjectDetail = lazy(() => import("../pages/management/ProjectDetail").then(m => ({ default: m.ProjectDetail })));

// Analysis workspace
const ScriptHubWizard = lazy(() => import("../pages/analysis/ScriptHubWizard").then(m => ({ default: m.ScriptHubWizard })));
const JobMonitor = lazy(() => import("../pages/analysis/JobMonitor").then(m => ({ default: m.JobMonitor })));

const AnalysisCenter = lazy(() => import("../pages/analysis/AnalysisCenter").then(m => ({ default: m.AnalysisCenter })));
const AnalysisToolPage = lazy(() => import("../pages/analysis/AnalysisToolPage").then(m => ({ default: m.AnalysisToolPage })));

// Auth & shared
const Register = lazy(() => import("../pages/auth/Register").then(m => ({ default: m.Register })));
const Account = lazy(() => import("../pages/auth/Account").then(m => ({ default: m.Account })));
const Login = lazy(() => import("../pages/auth/Login").then(m => ({ default: m.Login })));

// ── Layout ─────────────────────────────────────────────────────────────

function PageLoader() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
      <Skeleton height="48px" variant="text" width="40%" />
      <Skeleton height="120px" />
      <Skeleton height="200px" />
      <Skeleton height="160px" />
    </div>
  );
}

function AuthenticatedWorkspace() {
  const { user } = useAuth();
  return <AnalysisDataProvider key={user?.user_id ?? "guest"}><Shell /></AnalysisDataProvider>;
}

function Shell() {
  return (
    <div className="shell">
      <Sidebar />
      <main className="page-wrap">
        <ErrorBoundary>
          <Suspense fallback={<PageLoader />}>
            <Outlet />
          </Suspense>
        </ErrorBoundary>
      </main>
    </div>
  );
}

// ── App ────────────────────────────────────────────────────────────────

export function App() {
  return (
    <AuthProvider>
      <WorkspaceProvider>
        <ToastProvider>
          <Routes>
            <Route path="/" element={<Suspense fallback={<PageLoader />}><Navigate to="/analysis/center" replace /></Suspense>} />
            {/* Login — outside shell */}
            <Route path="/login" element={
              <Suspense fallback={<PageLoader />}>
                <Login />
              </Suspense>
            } />

            <Route path="/register" element={<Suspense fallback={<PageLoader />}><Register /></Suspense>} />

            {/* Shell layout — wraps all workspace pages */}
            <Route element={<ProtectedRoute allowUnauthenticated={false}><AuthenticatedWorkspace /></ProtectedRoute>}>
              {/* Root redirect */}


              {/* ── Management workspace ── */}
              <Route path="account" element={<Account />} />
              <Route path="management">
                <Route index element={<Navigate to="/analysis/center" replace />} />
                <Route path="projects" element={<Navigate to="/analysis/center" replace />} />
                <Route path="projects/:projectId" element={<ProjectDetail />} />
              </Route>

              {/* ── Analysis workspace ── */}
              <Route path="analysis">
                <Route index element={<Navigate to="/analysis/center" replace />} />
                <Route path="center" element={<AnalysisCenter />} />
                <Route path="tools/:toolId" element={<AnalysisToolPage />} />
                <Route path="script-hub" element={<ScriptHubWizard />} />
                <Route path="script-hub/jobs" element={<JobMonitor />} />
              </Route>

              {/* 404 */}
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </ToastProvider>
      </WorkspaceProvider>
    </AuthProvider>
  );
}

function NotFound() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "var(--spacing-lg)",
        padding: "var(--spacing-5xl) var(--spacing-xl)",
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontSize: "5rem",
          fontWeight: 700,
          color: "var(--text-tertiary)",
          lineHeight: 1,
        }}
      >
        404
      </div>
      <h2 style={{ margin: 0 }}>页面不存在</h2>
      <p style={{ color: "var(--text-secondary)", maxWidth: "360px" }}>
        您访问的页面不存在或已移动。
      </p>
      <a
        href="/analysis/center"
        style={{
          padding: "10px 24px",
          borderRadius: "var(--radius-control)",
          background: "var(--accent)",
          color: "#ffffff",
          fontWeight: 500,
          textDecoration: "none",
        }}
      >
        返回工作台
      </a>
    </div>
  );
}
