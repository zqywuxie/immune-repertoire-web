import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getAuthMe, login as apiLogin, logout as apiLogout, type AuthPrincipal } from "../api/auth";

interface AuthState {
  user: AuthPrincipal | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthPrincipal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const principal = await getAuthMe();
      setUser(principal);
    } catch (err) {
      // Not authenticated — silently set null, don't surface auth/not-found errors
      setUser(null);
      const status = (err as { status?: number }).status;
      if (status && ![401, 403, 404].includes(status)) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    const result = await apiLogin({ username, password });
    if (!result.success) {
      throw new Error(result.message || "Login failed");
    }
    setUser(result.user || { username, role: "user" });
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // Best-effort
    }
    setUser(null);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        login,
        logout,
        refresh,
        isAuthenticated: !!user,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
