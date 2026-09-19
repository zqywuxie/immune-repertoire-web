import { useAuth } from "../../shared/context/AuthContext";
export function Account() {
  const { user } = useAuth();
  return <section className="card"><h1>账号信息</h1><dl><dt>用户名</dt><dd>{user?.username}</dd><dt>邮箱</dt><dd>{user?.email || "未设置"}</dd></dl><p>项目、数据和分析结果按当前账号独立管理。</p></section>;
}
