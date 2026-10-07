import { useState } from "react";
import { Maximize2, Minus, Plus, RotateCcw } from "lucide-react";
import { Sheet } from "../../shared/components/Sheet";
import "./ResultImageViewer.css";

export function ResultImageViewer({ url, label = "输出图片" }: { url: string; label?: string }) {
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [zoom, setZoom] = useState(1);
  const retry = () => { setStatus("loading"); setAttempt(value => value + 1); };

  return <div className="result-image-viewer">
    <div className="result-image-toolbar">
      <span>{status === "ready" ? "可放大查看细节，原图保持不变。" : "图表预览"}</span>
      <button type="button" disabled={status !== "ready"} onClick={() => { setZoom(1); setExpanded(true); }}>
        <Maximize2 size={16} aria-hidden="true" />放大查看
      </button>
    </div>
    <div className="result-image-preview" aria-busy={status === "loading"}>
      {status === "loading" && <p role="status">正在加载图表…</p>}
      {status === "failed" ? <div role="alert" className="result-image-error">
        <p>图片加载失败。可重试，或打开原图检查文件。</p>
        <button type="button" onClick={retry}>重新加载</button>
        <a href={url} target="_blank" rel="noreferrer">打开原图</a>
      </div> : <img key={attempt} src={url} alt={label} loading="lazy"
        onLoad={() => setStatus("ready")} onError={() => setStatus("failed")} />}
    </div>
    <Sheet open={expanded} onClose={() => setExpanded(false)} title="图表放大查看">
      <div className="result-image-expanded">
        <p className="result-image-title">{label}</p>
        <div className="result-image-zoom-controls" role="group" aria-label="图表缩放">
          <button type="button" aria-label="缩小图表" disabled={zoom <= 1} onClick={() => setZoom(value => Math.max(1, value - .5))}><Minus size={16} /></button>
          <output aria-label="缩放比例">{Math.round(zoom * 100)}%</output>
          <button type="button" aria-label="放大图表" disabled={zoom >= 3} onClick={() => setZoom(value => Math.min(3, value + .5))}><Plus size={16} /></button>
          <button type="button" onClick={() => setZoom(1)}><RotateCcw size={16} aria-hidden="true" />适应窗口</button>
          <a href={url} target="_blank" rel="noreferrer">打开原图</a>
        </div>
        <div className="result-image-viewport">
          <img src={url} alt={`${label}（放大视图）`} style={{ width: `${zoom * 100}%` }} />
        </div>
      </div>
    </Sheet>
  </div>;
}
