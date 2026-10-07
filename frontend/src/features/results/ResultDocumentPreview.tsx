import { useEffect, useRef, useState } from "react";
import { Download, ExternalLink, RefreshCw } from "lucide-react";
import "./ResultDocumentPreview.css";

type Kind = "html" | "pdf";
type Props = {url: string; kind: Kind; label?: string; downloadUrl?: string};
type Phase = "checking" | "loading" | "ready" | "failed" | "unsupported";

function localUrl(url: string) {
  return new URL(url, window.location.href).origin === window.location.origin;
}
function frameUrl(url: string, attempt: number) {
  if (!attempt || !localUrl(url)) return url;
  const parsed = new URL(url, window.location.href);
  parsed.searchParams.set("_preview_retry", String(attempt));
  return parsed.href;
}
function loginUrl(url: string) {
  return /\/(login|register)\/?$/.test(new URL(url, window.location.href).pathname);
}

async function checkDocument(url: string, kind: Kind, signal: AbortSignal) {
  // External reports retain their native iframe behavior; they may not permit metadata requests.
  if (!localUrl(url)) return false;
  let response = await fetch(url, {method:"HEAD", credentials:"include", cache:"no-store", signal});
  await response.body?.cancel().catch(() => {});
  if ([405, 501].includes(response.status)) {
    response = await fetch(url, {credentials:"include", cache:"no-store", signal});
    await response.body?.cancel().catch(() => {}); // Only response metadata is used, never the full report body.
  }
  if ([404, 410].includes(response.status)) throw new Error("结果文件不存在或已移除。");
  if ([401, 403].includes(response.status) || (response.redirected && loginUrl(response.url))) throw new Error("当前登录状态或项目权限无法读取此报告，请重新登录或检查项目权限。");
  if (!response.ok) throw new Error("读取报告文件失败，请重试。（状态码 " + response.status + "）");
  if (response.headers.get("content-length") === "0") throw new Error("报告文件为空，请检查任务结果。");
  const type = (response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  if (type && type !== "application/octet-stream" && !(kind === "html" ? ["text/html","application/xhtml+xml"].includes(type) : type === "application/pdf")) {
    throw new Error(kind === "html" ? "此链接未返回网页报告，请检查任务结果。" : "此链接未返回 PDF 文档，请检查任务结果或登录状态。");
  }
  return /^\s*attachment(?:;|$)/i.test(response.headers.get("content-disposition") || "");
}

export function ResultDocumentPreview(props: Props) {
  const [attempt, setAttempt] = useState(0);
  return <DocumentLoad key={props.kind + ":" + props.url + ":" + attempt} {...props} attempt={attempt} onRetry={() => setAttempt(value => value + 1)} />;
}

function DocumentLoad({url, kind, label, downloadUrl, attempt, onRetry}: Props & {attempt: number; onRetry: () => void}) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [phase, setPhase] = useState<Phase>("checking");
  const [error, setError] = useState("");
  const [slow, setSlow] = useState(false);
  const [unsupported, setUnsupported] = useState("");
  const title = label ? label + (kind === "html" ? "（网页报告）" : "（文档查看器）") : kind === "html" ? "网页报告" : "文档查看器";
  useEffect(() => {
    const controller = new AbortController();
    checkDocument(url, kind, controller.signal).then(attachment => {
      if (controller.signal.aborted) return;
      if (attachment || (kind === "pdf" && navigator.pdfViewerEnabled === false)) {
        setUnsupported(attachment ? "此链接以下载方式提供文件，无法直接预览。" : "当前浏览器不支持内嵌 PDF，请在新标签页查看或下载文档。");
        setPhase("unsupported");
      } else setPhase("loading");
    }).catch(reason => {
      if (controller.signal.aborted) return;
      setError(reason instanceof TypeError ? "读取报告失败，可能是网络连接中断，请重试。" : reason.message || "读取报告文件失败，请重试。");
      setPhase("failed");
    });
    return () => controller.abort();
  }, [url, kind]);
  useEffect(() => {
    if (!["checking", "loading"].includes(phase)) return;
    const timer = window.setTimeout(() => setSlow(true), 30000);
    return () => window.clearTimeout(timer);
  }, [phase]);
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const failed = () => { setError("报告预览加载失败，请重新加载或在新标签页查看。"); setPhase("failed"); };
    frame.addEventListener("error", failed);
    return () => frame.removeEventListener("error", failed);
  }, [phase]);
  return <section className="result-document-preview" aria-label={kind === "html" ? "报告预览" : "文档预览"} aria-busy={phase === "checking" || phase === "loading"}>
    <div className="result-document-actions">
      <a href={url} target="_blank" rel="noreferrer"><ExternalLink size={15} aria-hidden="true" />{kind === "html" ? "在新标签页查看报告" : "在新标签页查看文档"}</a>
      {kind === "pdf" && <a href={downloadUrl || url} download target="_blank" rel="noreferrer"><Download size={15} aria-hidden="true" />下载文档</a>}
      <button type="button" onClick={onRetry}><RefreshCw size={15} aria-hidden="true" />重新加载</button>
    </div>
    {phase === "failed" && <p role="alert" className="result-document-error">{error}</p>}
    {phase === "unsupported" && <p role="status">{unsupported}</p>}
    {phase === "checking" && <p role="status">正在检查报告文件…</p>}
    {phase === "loading" && <p role="status">{kind === "html" ? "正在载入网页报告…" : "正在载入文档…"}</p>}
    {slow && ["checking","loading"].includes(phase) && <p role="status" className="result-document-notice">加载时间较长，可以继续等待、重新加载或在新标签页查看。</p>}
    {["loading","ready"].includes(phase) && <>
      <p className="result-document-hint">内容未显示时，可在新标签页查看{kind === "pdf" ? "或下载文档" : "报告"}。</p>
      <iframe ref={frameRef} src={frameUrl(url, attempt)} title={title} data-result-document={kind}
        sandbox={kind === "html" ? "allow-scripts allow-same-origin allow-downloads" : undefined}
        className={kind === "pdf" ? "result-document-pdf" : ""}
        onLoad={event => {
          if (kind === "html" && localUrl(url)) {
            try {
              const doc = event.currentTarget.contentDocument;
              if (!doc || loginUrl(doc.location.href)) {
                setError("浏览器未能显示报告或登录状态已失效，请在新标签页查看。");setPhase("failed");return;
              }
            } catch { setError("浏览器无法在此处显示报告，请在新标签页查看。");setPhase("failed");return; }
          }
          setSlow(false);setPhase("ready");
        }}
        />
    </>}
  </section>;
}
