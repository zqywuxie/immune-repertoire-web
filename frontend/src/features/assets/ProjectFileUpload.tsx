import { useEffect, useRef, useState } from "react";
import { FileUp, Upload } from "lucide-react";
import { uploadProjectAssets } from "../../shared/api/projects";
import { createUploadOperationId } from "../../shared/api/uploadOperations";
import { FileDropZone } from "../../shared/components/FileDropZone";
import "./DataManagement.css";

type Props = { projectId: string; onSuccess: () => void; onBusyChange?: (busy: boolean) => void; onPendingChange?: (count: number) => void; };
type FileEntry = { name: string; size: number; file: File; operationId: string; };
export function ProjectFileUpload({ projectId, onSuccess, onBusyChange, onPendingChange }: Props) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [collisions, setCollisions] = useState<string[]>([]);
  const [rows, setRows] = useState<{ name: string; stage: string; progress?: number }[]>([]);
  const controller = useRef<AbortController | null>(null);
  const attempted = useRef(new Set<string>());
  useEffect(() => { onPendingChange?.(files.length); }, [files.length, onPendingChange]);
  useEffect(() => () => { onPendingChange?.(0); onBusyChange?.(false); }, [onPendingChange, onBusyChange]);
  useEffect(() => { onBusyChange?.(busy); }, [busy, onBusyChange]);
  useEffect(() => () => controller.current?.abort(), []);
  async function handleUpload() {
    if (!files.length || busy) return;
    const aborter = new AbortController(); controller.current = aborter;
    setBusy(true); setMessage(""); setRows(files.map(item => ({ name: item.name, stage: "等待上传" })));
    let saved = 0; const errors: string[] = [];
    const row = (name: string, stage: string, progress?: number) => setRows(previous => previous.map(item => item.name === name ? { name, stage, progress } : item));
    for (const item of files) {
      if (aborter.signal.aborted) { row(item.name, "未开始，已保留选择"); continue; }
      try {
        row(item.name, "正在上传", 0);
        const retry = attempted.current.has(item.operationId);
        attempted.current.add(item.operationId);
        await uploadProjectAssets(projectId, { assetType: "project_file", files: [item.file], signal: aborter.signal,
          operationId: item.operationId, retry, onStatusCheck: () => row(item.name, "正在核对保存状态"),
          onProgress: percentage => row(item.name, percentage === 100 ? "已传输，正在保存" : "正在上传", percentage) });
        saved++; row(item.name, "已保存"); setFiles(previous => previous.filter(entry => entry.file !== item.file));
      } catch (reason) { const error = reason instanceof Error ? reason.message : "上传失败"; errors.push(error); row(item.name, error); }
    }
    controller.current = null; setBusy(false);
    setMessage(`已保存 ${saved} 个附件${errors.length ? `；${errors.join("；")}。剩余选择已保留，可重试。` : "。"}`);
    if (saved) onSuccess();
  }
  return <div className="data-section">
    <div className="data-section-header"><FileUp size={20} /><p>这些文件随项目保存，不参与分析输入。</p></div>
    <FileDropZone files={files} disabled={busy} multiple label="将项目文档、笔记、表格或附件拖到此处"
      onFilesAdded={incoming => {
        const entries = new Map(files.map(item => [item.name, item]));
        const skipped: string[] = [];
        for (const file of Array.from(incoming as FileList | File[])) {
          if (entries.has(file.name)) skipped.push(file.name);
          else entries.set(file.name, { file, name: file.name, size: file.size, operationId: createUploadOperationId() });
        }
        setCollisions([...new Set(skipped)]); setFiles([...entries.values()]);
      }}
      onRemoveFile={name => setFiles(previous => previous.filter(item => item.name !== name))} />
    {collisions.length > 0 && <p role="alert" className="data-error">以下同名文件未添加，已保留先前选择：{collisions.join("、")}。如需替换，请先移除原选择再添加。</p>}
    <div className="data-row-actions"><button className="btn btn-primary" disabled={busy || !files.length} onClick={handleUpload}><Upload size={15} />{busy ? "正在上传…" : `上传 ${files.length} 个附件`}</button>
      {busy && <button className="btn btn-secondary" onClick={() => controller.current?.abort()}>取消剩余上传</button>}</div>
    {rows.length > 0 && <ul className="data-upload-progress" aria-live="polite">{rows.map(item => <li key={item.name}><span>{item.name}</span><span>{item.stage}{typeof item.progress === "number" ? ` · ${item.progress}%` : ""}</span></li>)}</ul>}
    {message && <p role="status">{message}</p>}
  </div>;
}
