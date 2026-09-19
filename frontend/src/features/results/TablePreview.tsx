import { ServerTablePreview } from "./ServerTablePreview";
import { useEffect, useMemo, useState } from "react";

const MAX_BYTES = 2 * 1024 * 1024;
const MAX_ROWS = 1000;

// Keep values as text so sample identifiers and scientific precision are preserved.
export function parseTable(text: string, delimiter = ",", incomplete = false) {
  const rows: string[][] = [];
  let row: string[] = [], value = "", quoted = false;
  text = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      if (quoted && text[i + 1] === '"') { value += '"'; i++; }
      else if (quoted || !value) quoted = !quoted;
      else value += ch;
    } else if (ch === delimiter && !quoted) { row.push(value); value = ""; }
    else if ((ch === "\n" || ch === "\r") && !quoted) {
      row.push(value); rows.push(row); row = []; value = "";
      if (ch === "\r" && text[i + 1] === "\n") i++;
      if (rows.length > MAX_ROWS) return { rows, limited: i < text.length - 1 || incomplete };
    } else value += ch;
  }
  if (!incomplete && quoted) throw new Error("数据表引号不完整，请下载原文件检查。");
  if (!incomplete && (row.length || value)) { row.push(value); rows.push(row); }
  return { rows: rows.slice(0, MAX_ROWS + 1), limited: incomplete || rows.length > MAX_ROWS + 1 };
}

async function readPreview(url: string, signal: AbortSignal, kind?: string) {
  const response = await fetch(url, { credentials: "include", signal });
  if (!response.ok) throw new Error(response.status === 404 ? "结果文件不存在或已移除。" : "读取数据表失败，请重试。");
  if ((response.headers.get("content-type") || "").includes("text/html")) throw new Error("此链接未返回数据表，请检查任务结果。");
  if (!response.body) throw new Error("当前浏览器无法预览，请下载原文件。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let text = "", bytes = 0, limited = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) { text += decoder.decode(); break; }
      const remaining = MAX_BYTES - bytes;
      text += decoder.decode(value.subarray(0, remaining), { stream: true });
      bytes += value.byteLength;
      if (bytes >= MAX_BYTES) { limited = true; break; }
    }
  } finally { await reader.cancel(); }
  return parseTable(text, (kind === "tsv" || new URL(url, window.location.href).pathname.toLowerCase().endsWith(".tsv")) ? "\t" : ",", limited);
}

export function TablePreview({ url, kind, jobId }: { url: string; kind?: string; jobId?: string }) {
  return jobId ? <ServerTablePreview key={`${jobId}:${url}`} jobId={jobId} url={url} /> : <LocalTablePreview key={url} url={url} kind={kind} />;
}

function LocalTablePreview({ url, kind }: { url: string; kind?: string }) {
  const [data, setData] = useState<{ rows: string[][]; limited: boolean } | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError(""); setPage(0); setQuery("");
    readPreview(url, controller.signal, kind).then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof TypeError ? "读取失败，可能是网络中断或文件编码不支持，请下载原文件。" : reason.message); });
    return () => controller.abort();
  }, [url, kind, attempt]);
  const rows = useMemo(() => (data?.rows.slice(1) || []).filter(row => row.some(value => value.toLocaleLowerCase().includes(query.toLocaleLowerCase()))), [data, query]);
  if (error) return <div role="alert">{error} <button type="button" onClick={() => setAttempt(v => v + 1)}>重新加载</button></div>;
  if (!data) return <p role="status">正在读取数据表…</p>;
  if (!data.rows.length) return <p>数据表为空。</p>;
  const pages = Math.max(1, Math.ceil(rows.length / 25));
  return <div style={{ display: "grid", gap: 12, minWidth: 0 }}>
    <label style={{ display: "grid", gap: 6 }}>筛选预览内容 <input style={{ width: "100%", minWidth: 0, boxSizing: "border-box", padding: "8px 10px", border: "1px solid var(--separator)", borderRadius: "var(--radius-control)", background: "var(--bg-root)", color: "var(--text-primary)" }} aria-label="筛选预览内容" value={query} onChange={e => { setQuery(e.target.value); setPage(0); }} placeholder="输入样本、分组或数值" /></label>
    <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.8rem" }}>
      {data.limited ? "仅预览前 1000 行或前 2 MB 内的完整记录；筛选仅作用于预览内容，完整数据请下载。" : `共 ${Math.max(0, data.rows.length - 1)} 行数据。`}
    </p>
    <div style={{ overflow: "auto", maxHeight: 460, border: "1px solid var(--separator)", borderRadius: "var(--radius-control)" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.82rem" }}>
        <caption style={{ textAlign: "left", padding: 8 }}>数据表预览</caption>
        <thead><tr>{data.rows[0].map((column, i) => <th scope="col" key={i} style={{ padding: 10, textAlign: "left", background: "var(--bg-root)", whiteSpace: "nowrap" }}>{column || `第 ${i + 1} 列`}</th>)}</tr></thead>
        <tbody>{rows.slice(page * 25, (page + 1) * 25).map((row, i) => <tr key={i}>{row.map((value, j) => <td key={j} style={{ padding: 10, borderTop: "1px solid var(--separator)", whiteSpace: "pre-wrap", maxWidth: 360, overflowWrap: "anywhere" }}>{value}</td>)}</tr>)}</tbody>
      </table>
    </div>
    {!rows.length && <p>{query ? "没有匹配的记录。" : "数据表只有表头，没有数据记录。"}</p>}
    <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
      <button type="button" disabled={page === 0} onClick={() => setPage(v => v - 1)}>上一页</button>
      <span>第 {page + 1} / {pages} 页 · 匹配 {rows.length} 行</span>
      <button type="button" disabled={page + 1 >= pages} onClick={() => setPage(v => v + 1)}>下一页</button>
    </div>
  </div>;
}
