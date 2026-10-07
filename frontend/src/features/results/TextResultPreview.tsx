import { useEffect, useRef, useState } from "react";
import "./TextResultPreview.css";

const MAX_PREVIEW_BYTES = 2 * 1024 * 1024;
const MAX_TEXT_LINES = 2000;
type TextKind = "json" | "text" | "log";
type PreviewRange = "start" | "end";
type Preview = { text: string; limited: boolean; linesLimited: boolean; invalidJson: boolean };

function linePreview(text: string, range: PreviewRange) {
  let cursor = range === "end" ? text.length - (text.endsWith("\n") ? 2 : 1) : 0;
  for (let line = 0; line < MAX_TEXT_LINES; line += 1) {
    if (range === "end" && cursor < 0) return { text, linesLimited: false };
    const next = range === "end" ? text.lastIndexOf("\n", cursor) : text.indexOf("\n", cursor);
    if (next < 0) return { text, linesLimited: false };
    cursor = range === "end" ? next - 1 : next + 1;
    if (range === "start" && cursor === text.length) return { text, linesLimited: false };
  }
  return { text: range === "end" ? text.slice(cursor + 2) : text.slice(0, cursor), linesLimited: true };
}

async function readPreview(url: string, signal: AbortSignal, kind: TextKind, range: PreviewRange): Promise<Preview> {
  const name = kind === "json" ? "结构化数据" : kind === "log" ? "日志" : "文本";
  const local = new URL(url, window.location.href).origin === window.location.origin;
  const headers = kind !== "json" && local ? { Range: range === "end" ? `bytes=-${MAX_PREVIEW_BYTES}` : `bytes=0-${MAX_PREVIEW_BYTES - 1}` } : undefined;
  const response = await fetch(url, { credentials: "include", signal, cache: "no-store", headers });
  const contentRange = response.headers.get("content-range") || "";
  if (kind !== "json" && response.status === 416 && /^bytes \*\/0$/i.test(contentRange)) {
    await response.body?.cancel();
    return { text: "", limited: false, linesLimited: false, invalidJson: false };
  }
  if (!response.ok) {
    await response.body?.cancel();
    if (response.status === 404 || response.status === 410) throw new Error("结果文件不存在或已移除。");
    if (response.status === 401 || response.status === 403) throw new Error("当前无法访问此文件，请检查登录状态或项目权限。");
    throw new Error(`读取${name}失败（响应状态：${response.status}），请重试。`);
  }
  if ((response.headers.get("content-type") || "").toLowerCase().includes("text/html")) {
    await response.body?.cancel();
    throw new Error(`此链接返回了网页，没有返回${name}，请检查任务结果。`);
  }
  if (!response.body) throw new Error("当前浏览器无法预览，请下载原文件。");
  const recordedRange = contentRange.match(/^bytes (\d+)-(\d+)\/(\d+)$/i);
  const partial = response.status === 206 && (!recordedRange || Number(recordedRange[1]) > 0 || Number(recordedRange[2]) + 1 < Number(recordedRange[3]));
  const isTail = range === "end" && response.status === 206 && recordedRange && Number(recordedRange[2]) + 1 === Number(recordedRange[3]);
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let text = "", bytes = 0, limited = Boolean(partial), skipPrefix = Boolean(isTail && Number(recordedRange?.[1]) > 0), skipped = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) { text += decoder.decode(); break; }
      const remaining = MAX_PREVIEW_BYTES - bytes;
      let chunk = value.subarray(0, remaining);
      bytes += chunk.byteLength;
      // A suffix range may start within a valid multi-byte UTF-8 character.
      if (skipPrefix) {
        let start = 0;
        while (start < chunk.length && skipped < 3 && (chunk[start] & 0xc0) === 0x80) { start += 1; skipped += 1; }
        skipPrefix = start === chunk.length && skipped < 3;
        chunk = chunk.subarray(start);
      }
      text += decoder.decode(chunk, { stream: true });
      if (value.byteLength > remaining || bytes === MAX_PREVIEW_BYTES) { limited = true; break; }
    }
  } finally { await reader.cancel().catch(() => {}); }
  if (kind !== "json" && range === "end" && ((response.status === 206 && !isTail) || (response.status !== 206 && limited))) {
    throw new Error("此接口不支持文件末尾预览，请切换到文件开头或下载完整文件。");
  }
  let invalidJson = false;
  // Render original values; parsing is only a syntax check for complete JSON.
  if (kind === "json" && text.trim() && !limited) {
    try { JSON.parse(text); } catch { invalidJson = true; }
  }
  const lines = kind === "json" ? { text, linesLimited: false } : linePreview(text, range);
  return { ...lines, limited, invalidJson };
}

export function TextResultPreview({ url, kind = "json" }: { url: string; kind?: TextKind }) {
  const originalRef = useRef<HTMLPreElement>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [range, setRange] = useState<PreviewRange>(kind === "log" ? "end" : "start");
  const name = kind === "json" ? "结构化数据" : kind === "log" ? "日志" : "文本";
  useEffect(() => {
    const controller = new AbortController();
    setPreview(null); setError("");
    readPreview(url, controller.signal, kind, range)
      .then(result => { if (!controller.signal.aborted) setPreview(result); })
      .catch(reason => {
        if (!controller.signal.aborted) setError(reason instanceof TypeError
          ? "读取失败，请检查网络和文件编码，或下载原文件。"
          : reason instanceof Error ? reason.message : `读取${name}失败，请重试。`);
      });
    return () => controller.abort();
  }, [url, kind, range, attempt, name]);

  useEffect(() => {
    if (preview && originalRef.current) {
      originalRef.current.scrollTop = kind === "log" && range === "end" ? originalRef.current.scrollHeight : 0;
    }
  }, [preview, kind, range]);

  return <section className="text-result-preview" aria-label={name + "预览"} aria-busy={!preview && !error}>
    {kind !== "json" && <div className="text-result-toolbar">
      {kind === "log" && <label>预览范围<select aria-label="日志预览范围" className="input" value={range} onChange={event => setRange(event.target.value as PreviewRange)}><option value="end">文件末尾</option><option value="start">文件开头</option></select></label>}
      <button className="btn btn-secondary" type="button" disabled={!preview && !error} onClick={() => setAttempt(value => value + 1)}>重新读取{name}</button>
    </div>}
    {!preview && !error && <p role="status">正在读取{name}…</p>}
    {error && <div role="alert" className="text-result-error"><p>{error}</p>
      {kind === "json" && <button type="button" onClick={() => setAttempt(value => value + 1)}>重新加载</button>}
    </div>}
    {preview && <>
      {preview.limited && <p role="status" className="text-result-notice">仅预览{range === "end" ? "末尾" : "前"} 2 MB，内容可能在中间截断；完整内容请下载原文件。</p>}
      {preview.linesLimited && <p role="status" className="text-result-notice">当前显示{range === "end" ? "最后" : "最前"} 2000 行，完整内容请下载原文件。</p>}
      {preview.invalidJson && <p role="status" className="text-result-notice">文件内容无法按 JSON 解析，以下显示文件原文；请下载后检查格式。</p>}
      {!preview.text.trim() ? <p>{name}文件为空。</p> : <>
        <p className="text-result-hint">按文件原文显示数值和编号。</p>
        <pre ref={originalRef} tabIndex={0} aria-label="文件原文"><code>{preview.text}</code></pre>
      </>}
    </>}
  </section>;
}
