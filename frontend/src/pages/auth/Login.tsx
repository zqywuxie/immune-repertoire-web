import { useState, useEffect } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { LogIn, AlertCircle } from "lucide-react";
import { useAuth } from "../../shared/context/AuthContext";

import { getAuthOptions } from "../../shared/api/auth";

export function Login() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { login, isAuthenticated, loading: checkingAuth } = useAuth();

  const [registrationEnabled, setRegistrationEnabled] = useState(false);
  useEffect(() => { getAuthOptions().then(options => setRegistrationEnabled(options.registration_enabled)).catch(() => {}); }, []);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const requested = searchParams.get("redirect") || "/analysis/center";
  const redirect = requested.startsWith("/") && !requested.startsWith("//") && !requested.includes("\\") && !/^\/(login|register|auth)(\/|\?|$)/.test(requested)
    ? requested : "/analysis/center";
  if (checkingAuth) return <div role="status">正在进入工作台…</div>;
  if (isAuthenticated) return <Navigate to={redirect} replace />;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError("请输入用户名和密码。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await login(username.trim(), password);
      navigate(redirect, { replace: true });
    } catch (err) {
      setError(err instanceof Error && /[\u4e00-\u9fff]/.test(err.message) ? err.message : "登录失败，请检查用户名和密码，或联系管理员。");
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
            免
          </div>
          <h2 style={{ margin: 0, fontSize: "1.3rem" }}>
            免疫组库分析平台
          </h2>
          <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
            登录您的账号
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
            用户名
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              autoFocus
              autoComplete="username"
              className="input"
              disabled={loading}
            />
          </label>

          <label className="field-label">
            密码
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
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
            {loading ? "正在登录…" : "登录"}
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
          {registrationEnabled ? <Link to="/register">还没有账号？创建账号</Link> : "请使用已有账号登录"}
        </p>
      </div>
    </div>
  );
}
