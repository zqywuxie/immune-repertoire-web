import { useState, useEffect } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { getAuthOptions, register } from "../../shared/api/auth";
import { useAuth } from "../../shared/context/AuthContext";

export function Register() {
  const { refresh, isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [fields, setFields] = useState({ username: "", email: "", password: "", confirm_password: "" });
  useEffect(() => { getAuthOptions().then(value => setEnabled(value.registration_enabled)).catch(() => setError("暂时无法获取注册设置，请刷新重试。")); }, []);
  if (loading) return <div role="status">正在检查登录状态…</div>;
  if (isAuthenticated) return <Navigate to="/analysis/center" replace />;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (fields.password !== fields.confirm_password) { setError("两次输入的密码不一致。"); return; }
    setBusy(true); setError("");
    try {
      await register(fields);
      await refresh();
      navigate("/analysis/center", { replace: true });
    } catch (failure) { setError(failure instanceof Error ? failure.message : "注册失败，请重试。"); }
    finally { setBusy(false); }
  }
  return <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "var(--spacing-xl)", background: "var(--bg-root)" }}>
    <section className="card" style={{ width: "100%", maxWidth: 440, padding: "var(--spacing-2xl)" }}>
      <h1>创建账号</h1><p>在自己的项目中管理数据、运行分析和查看结果。</p>
      {error && <p role="alert" style={{ color: "var(--danger)" }}>{error}</p>}
      {enabled === false ? <p>当前未开放注册，请联系管理员。</p> : <form onSubmit={submit} style={{ display: "grid", gap: "var(--spacing-md)" }}>
        {([
          ["username", "用户名", "text", "username"],
          ["email", "邮箱", "email", "email"],
          ["password", "密码", "password", "new-password"],
          ["confirm_password", "确认密码", "password", "new-password"],
        ] as const).map(([key, label, type, autoComplete]) => <label className="field-label" key={key}>{label}
          <input className="input" type={type} autoComplete={autoComplete} required disabled={busy} value={fields[key]}
            minLength={key.includes("password") ? 6 : key === "username" ? 3 : undefined}
            maxLength={key.includes("password") ? 128 : key === "username" ? 80 : 255}
            onChange={event => setFields({ ...fields, [key]: event.target.value })} />
        </label>)}
        <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>用户名支持中文、字母、数字、下划线和短横线；密码至少 6 位。</p>
        <button className="btn btn-primary" disabled={busy || enabled !== true}>{busy ? "正在创建…" : "注册并进入分析中心"}</button>
      </form>}
      <p>已有账号？<Link to="/login">返回登录</Link></p>
    </section>
  </main>;
}
