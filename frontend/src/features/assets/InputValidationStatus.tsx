import { useEffect, useState } from "react";
import { listProjectAssets } from "../../shared/api/projects";
import { apiClient } from "../../shared/api/client";

type Row = { id: string; name: string; status: string; message: string };
const labels: Record<string, string> = { valid: "校验通过", pending: "等待校验", invalid: "校验未通过", needs_mapping: "需要确认列映射", unknown: "首次使用时校验" };
export function InputValidationStatus({ projectId, revision }: { projectId: string; revision: number }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        apiClient.invalidatePath(`/api/projects/${projectId}/assets`);
        const result = await listProjectAssets(projectId, { pageSize: 200 });
        if (!active) return;
        const next = result.assets.filter(asset => ["pep", "profile", "datapoint", "transcriptome", "deconvolution", "cibersort"].includes(asset.asset_type)).map(asset => {
          const metadata = (asset.metadata || {}) as Record<string, any>;
          const validation = metadata.validation || {};
          return { id: asset.id, name: asset.original_name, status: validation.status || "unknown", message: (validation.summary?.errors || []).join("；") || validation.message || "" };
        });
        setRows(next); setError("");
        if (next.some(row => row.status === "pending")) timer = setTimeout(load, 5000);
      } catch { if (active) setError("校验状态暂时无法读取，请重新选择项目后重试。"); }
    }
    load();
    return () => { active = false; clearTimeout(timer); };
  }, [projectId, revision]);
  return <div aria-live="polite">{error && <p role="alert">{error}</p>}{rows.length > 0 && <details><summary>已上传 {rows.length} 个输入文件 · 查看校验状态</summary><ul>{rows.map(row => <li key={row.id}><strong>{row.name}</strong> · {labels[row.status] || row.status}{row.message && <p>{row.message}</p>}</li>)}</ul></details>}</div>;
}
