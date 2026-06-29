import { Routes, Route, Outlet } from "react-router-dom";
import { Suspense, lazy } from "react";
import { Database, FlaskConical, LayoutDashboard } from "lucide-react";
import { Rail } from "../shared/components/Rail";
import { ErrorBoundary } from "../shared/components/ErrorBoundary";
import { Skeleton } from "../shared/components/Skeleton";
import "./App.css";

const Dashboard = lazy(() => import("./Dashboard").then(m => ({ default: m.Dashboard })));
const DatabasePage = lazy(() => import("./Database").then(m => ({ default: m.DatabasePage })));
const ScriptHub = lazy(() => import("./ScriptHub").then(m => ({ default: m.ScriptHub })));

const NAV_LINKS = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/database", icon: Database, label: "Database" },
  { to: "/scripthub", icon: FlaskConical, label: "Script Hub" },
];

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

export function App() {
  return (
    <Routes>
      <Route
        element={
          <div className="shell">
            <Rail links={NAV_LINKS} />
            <main className="page-wrap">
              <ErrorBoundary>
                <Suspense fallback={<PageLoader />}>
                  <Outlet />
                </Suspense>
              </ErrorBoundary>
            </main>
          </div>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="database" element={<DatabasePage />} />
        <Route path="database/:projectId" element={<DatabasePage />} />
        <Route path="scripthub" element={<ScriptHub />} />
        <Route
          path="*"
          element={<NotFound />}
        />
      </Route>
    </Routes>
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
        href="/"
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
