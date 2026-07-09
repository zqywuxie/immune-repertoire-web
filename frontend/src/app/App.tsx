import { Routes, Route, Outlet, Navigate } from "react-router-dom";
import { Suspense, lazy } from "react";
import { ErrorBoundary } from "../shared/components/ErrorBoundary";
import { Skeleton } from "../shared/components/Skeleton";
import { Sidebar } from "../shared/components/Sidebar";
import { WorkspaceProvider } from "../shared/context/WorkspaceContext";
import { AuthProvider } from "../shared/context/AuthContext";
import { ToastProvider } from "../shared/hooks/useToast";
import { ProtectedRoute } from "../shared/components/ProtectedRoute";
import "./App.css";

// ── Lazy-loaded pages ──────────────────────────────────────────────────

// Management workspace
const ManagementDashboard = lazy(() => import("../pages/management/ManagementDashboard").then(m => ({ default: m.ManagementDashboard })));
const ProjectLibrary = lazy(() => import("../pages/management/ProjectLibrary").then(m => ({ default: m.ProjectLibrary })));
const ProjectDetail = lazy(() => import("../pages/management/ProjectDetail").then(m => ({ default: m.ProjectDetail })));
const SampleRegistry = lazy(() => import("../pages/management/SampleRegistry").then(m => ({ default: m.SampleRegistry })));

// Analysis workspace
const UnifiedAnalysis = lazy(() => import("../pages/analysis/UnifiedAnalysis").then(m => ({ default: m.UnifiedAnalysis })));
const ScriptHubWizard = lazy(() => import("../pages/analysis/ScriptHubWizard").then(m => ({ default: m.ScriptHubWizard })));
const JobMonitor = lazy(() => import("../pages/analysis/JobMonitor").then(m => ({ default: m.JobMonitor })));
const StatisticalComparison = lazy(() => import("../pages/analysis/StatisticalComparison").then(m => ({ default: m.StatisticalComparison })));
const PdfExtractor = lazy(() => import("../pages/analysis/PdfExtractor").then(m => ({ default: m.PdfExtractor })));
const PptTools = lazy(() => import("../pages/analysis/PptTools").then(m => ({ default: m.PptTools })));

// Auth & shared
const Login = lazy(() => import("../pages/auth/Login").then(m => ({ default: m.Login })));
const SettingsPage = lazy(() => import("../pages/Settings").then(m => ({ default: m.Settings })));

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
            {/* Login — outside shell */}
            <Route path="/login" element={
              <Suspense fallback={<PageLoader />}>
                <Login />
              </Suspense>
            } />

            {/* Shell layout — wraps all workspace pages */}
            <Route element={<ProtectedRoute><Shell /></ProtectedRoute>}>
              {/* Root redirect */}
              <Route index element={<Navigate to="/management" replace />} />

              {/* ── Management workspace ── */}
              <Route path="management">
                <Route index element={<ManagementDashboard />} />
                <Route path="projects" element={<ProjectLibrary />} />
                <Route path="projects/:projectId" element={<ProjectDetail />} />
                <Route path="samples" element={<SampleRegistry />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>

              {/* ── Analysis workspace ── */}
              <Route path="analysis">
                <Route index element={<UnifiedAnalysis />} />
                <Route path="script-hub" element={<ScriptHubWizard />} />
                <Route path="script-hub/jobs" element={<JobMonitor />} />
                <Route path="statistical" element={<StatisticalComparison />} />
                <Route path="pdf-extractor" element={<PdfExtractor />} />
                <Route path="ppt-tools" element={<PptTools />} />
                <Route path="settings" element={<SettingsPage />} />
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
      <h2 style={{ margin: 0 }}>Page not found</h2>
      <p style={{ color: "var(--text-secondary)", maxWidth: "360px" }}>
        The page you're looking for doesn't exist or has been moved.
      </p>
      <a
        href="/management"
        style={{
          padding: "10px 24px",
          borderRadius: "var(--radius-control)",
          background: "var(--accent)",
          color: "#ffffff",
          fontWeight: 500,
          textDecoration: "none",
        }}
      >
        Go to Dashboard
      </a>
    </div>
  );
}
