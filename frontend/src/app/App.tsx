import { Routes, Route, Outlet } from "react-router-dom";
import { Database, FlaskConical, LayoutDashboard } from "lucide-react";
import { Rail } from "../shared/components/Rail";
import { ErrorBoundary } from "../shared/components/ErrorBoundary";
import { Dashboard } from "./Dashboard";
import { DatabasePage } from "./Database";
import { ScriptHub } from "./ScriptHub";
import "./App.css";

const NAV_LINKS = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/database", icon: Database, label: "Database" },
  { to: "/scripthub", icon: FlaskConical, label: "Script Hub" },
];

export function App() {
  return (
    <Routes>
      <Route
        element={
          <div className="shell">
            <Rail links={NAV_LINKS} />
            <main className="page-wrap">
              <ErrorBoundary>
                <Outlet />
              </ErrorBoundary>
            </main>
          </div>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="database" element={<DatabasePage />} />
        <Route path="database/:projectId" element={<DatabasePage />} />
        <Route path="scripthub" element={<ScriptHub />} />
      </Route>
    </Routes>
  );
}
