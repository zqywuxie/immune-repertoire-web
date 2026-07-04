import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Skeleton } from "./Skeleton";

type Props = {
  children: React.ReactNode;
  /** If true, skip auth check (for dev mode where backend may not require auth). */
  allowUnauthenticated?: boolean;
};

export function ProtectedRoute({ children, allowUnauthenticated = true }: Props) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)", padding: "var(--spacing-3xl)" }}>
        <Skeleton height="48px" variant="text" width="40%" />
        <Skeleton height="120px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  if (!isAuthenticated && !allowUnauthenticated) {
    return <Navigate to={`/login?redirect=${encodeURIComponent(location.pathname)}`} replace />;
  }

  return <>{children}</>;
}
