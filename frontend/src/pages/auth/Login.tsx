import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { LogIn, AlertCircle } from "lucide-react";
import { useAuth } from "../../shared/context/AuthContext";

export function Login() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { login, isAuthenticated } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Redirect if already authenticated
  if (isAuthenticated) {
    const redirect = searchParams.get("redirect") || "/management";
    navigate(redirect, { replace: true });
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError("Username and password are required.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await login(username.trim(), password);
      const redirect = searchParams.get("redirect") || "/management";
      navigate(redirect, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg-root)",
        padding: "var(--spacing-xl)",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "400px",
          background: "var(--bg-elevated)",
          borderRadius: "var(--radius-card)",
          boxShadow: "var(--shadow-lg)",
          padding: "var(--spacing-3xl)",
        }}
      >
        {/* Brand */}
        <div style={{ textAlign: "center", marginBottom: "var(--spacing-2xl)" }}>
          <div
            style={{
              width: "56px",
              height: "56px",
              margin: "0 auto var(--spacing-md)",
              borderRadius: "var(--radius-control)",
              background: "var(--accent)",
              color: "#fff",
              display: "grid",
              placeItems: "center",
              fontSize: "1.4rem",
              fontWeight: 800,
              letterSpacing: "0.04em",
            }}
          >
            IR
          </div>
          <h2 style={{ margin: 0, fontSize: "1.3rem" }}>
            Immune Repertoire Platform
          </h2>
          <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
            Sign in to your account
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
          {error && (
            <div
              role="alert"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--spacing-sm)",
                padding: "var(--spacing-md)",
                borderRadius: "var(--radius-control)",
                background: "color-mix(in srgb, var(--danger) 15%, transparent)",
                border: "1px solid var(--danger)",
                color: "var(--danger)",
                fontSize: "0.85rem",
              }}
            >
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          <label className="field-label">
            Username
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter username"
              autoFocus
              autoComplete="username"
              className="input"
              disabled={loading}
            />
          </label>

          <label className="field-label">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              autoComplete="current-password"
              className="input"
              disabled={loading}
            />
          </label>

          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary"
            style={{ width: "100%", justifyContent: "center", padding: "10px 20px" }}
          >
            <LogIn size={16} />
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>

        {/* Dev mode note */}
        <p
          style={{
            textAlign: "center",
            marginTop: "var(--spacing-lg)",
            fontSize: "0.75rem",
            color: "var(--text-tertiary)",
          }}
        >
          Development mode: token-based authentication via <code>API_AUTH_TOKEN</code>
        </p>
      </div>
    </div>
  );
}
