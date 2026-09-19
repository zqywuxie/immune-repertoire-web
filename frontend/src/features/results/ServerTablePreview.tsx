import { useEffect, useState } from "react";

interface TablePage { columns: string[]; rows: string[][]; total_rows: number; matched_rows: number; offset: number; limit: number }
const control = { padding: "8px 10px", border: "1px solid var(--separator)", borderRadius: "var(--radius-control)", background: "var(--bg-root)", color: "var(--text-primary)" };

export function ServerTablePreview({ jobId, url }: { jobId: string; url: string }) {
  const [data, setData] = useState<TablePage | null>(null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setData(null);
    fetch(`/api/jobs/${encodeURIComponent(jobId)}/table-preview`, {
      method: "POST", credentials: "include", signal: controller.signal,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url, offset: page * 25, limit: 25, query }),
    }).then(async response => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "读取数据表失败，请重试。");
      return payload as TablePage;
    }).then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason.message || "读取数据表失败，请重试。"); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [jobId, url, query, page, attempt]);
  const pages = Math.max(1, Math.ceil((data?.matched_rows || 0) / 25));
  return <div style={{ display: "grid", gap: 12, minWidth: 0 }}>
    <form onSubmit={event => { event.preventDefault(); setQuery(draft.trim()); setPage(0); }} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end" }}>
      <label style={{ display: "grid", gap: 6, flex: "1 1 180px", minWidth: 0 }}>筛选全部数据
        <input style={{ ...control, width: "100%", boxSizing: "border-box" }} aria-label="筛选全部数据" value={draft} onChange={event => setDraft(event.target.value)} placeholder="输入样本、分组或数值" />
      </label>
      <button style={control} type="submit" disabled={loading}>筛选</button>
      {query && <button style={control} type="button" onClick={() => { setDraft(""); setQuery(""); setPage(0); }}>清除筛选</button>}
    </form>
    {loading && <p role="status">正在读取完整数据表…</p>}
    {error && <p role="alert">{error} <button type="button" onClick={() => setAttempt(value => value + 1)}>重新加载</button></p>}
    {data && <>
      <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.8rem" }}>共 {data.total_rows} 行 · 匹配 {data.matched_rows} 行 · 每页 25 行</p>
      {!data.columns.length ? <p>数据表为空。</p> : <div style={{ overflow: "auto", maxHeight: 460, border: "1px solid var(--separator)", borderRadius: "var(--radius-control)" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.82rem" }}>
          <caption style={{ textAlign: "left", padding: 8 }}>分析结果数据表</caption>
          <thead><tr>{data.columns.map((column, index) => <th scope="col" key={index} style={{ padding: 10, textAlign: "left", background: "var(--bg-root)", whiteSpace: "nowrap" }}>{column || `第 ${index + 1} 列`}</th>)}</tr></thead>
          <tbody>{data.rows.map((row, index) => <tr key={index}>{row.map((value, column) => <td key={column} style={{ padding: 10, borderTop: "1px solid var(--separator)", whiteSpace: "pre-wrap", maxWidth: 360, overflowWrap: "anywhere" }}>{value}</td>)}</tr>)}</tbody>
        </table>
      </div>}
      {!data.rows.length && data.columns.length > 0 && <p>{query ? "没有匹配的记录。" : "当前页没有数据记录。"}</p>}
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <button style={control} type="button" disabled={loading || page === 0} onClick={() => setPage(value => value - 1)}>上一页</button>
        <span>第 {page + 1} / {pages} 页</span>
        <button style={control} type="button" disabled={loading || page + 1 >= pages} onClick={() => setPage(value => value + 1)}>下一页</button>
      </div>
    </>}
  </div>;
}
