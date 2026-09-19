import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../../shared/hooks/useApi";
import { useJobResult } from "../../shared/hooks/useJobResult";
import { listProjects } from "../../shared/api/projects";
import { submitJob } from "../../shared/api/jobs";
import { statisticalPayload } from "../../shared/api/statistical";
import { uploadDataFile, type UploadedFile as StatisticalFile } from "../../shared/api/files";
import { PageHeader } from "../../shared/components/PageHeader";
import { ResultViewer } from "../../features/results/ResultViewer";

type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue => value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
const statusLabels: Record<string, string> = { queued: "正在排队", running: "正在分析", completed: "分析完成", failed: "分析失败", cancelled: "任务已取消", interrupted: "任务已中断", unknown: "状态读取失败" };

export function StatisticalComparison() {
  const [params, setParams] = useSearchParams();
  const [project, setProject] = useState("");
  const [files, setFiles] = useState<StatisticalFile[]>([]);
  const [value, setValue] = useState("");
  const [group, setGroup] = useState("");
  const [kind, setKind] = useState<"statistics" | "boxplot">("statistics");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const projects = useApi(listProjects, []);
  const task = useJobResult(params.get("job"));
  const active = !!task.jobId && !task.error && !["completed", "failed", "cancelled", "interrupted"].includes(task.status);
  const locked = busy || active;
  const columns = files.length ? files[0].columns.filter(column => files.every(file => file.columns.includes(column))) : [];

  async function upload(incoming: File[]) {
    if (!incoming.length || !project || locked) return;
    setBusy(true); setError("");
    const names = new Set(files.map(file => file.name));
    try {
      for (const file of incoming) {
        if (names.has(file.name)) throw new Error(`文件名重复：${file.name}。请重命名后上传。`);
        const uploaded = await uploadDataFile(file, project);
        setFiles(previous => [...previous, uploaded]);
        names.add(file.name);
      }
    } catch (error) { setError(error instanceof Error ? error.message : "上传失败，已上传的文件仍保留。请重新选择失败的文件。"); }
    finally { setBusy(false); }
  }

  async function run() {
    setError("");
    try {
      if (!project) throw new Error("请选择项目。");
      const request = statisticalPayload(files, value, group, kind);
      setBusy(true);
      const submitted = await submitJob({ ...request, projectId: project });
      if (!submitted.success || !submitted.job_id) throw new Error("任务未成功提交，请重试。");
      setParams({ job: submitted.job_id });
    } catch (error) { setError(error instanceof Error ? error.message : "提交失败"); }
    finally { setBusy(false); }
  }

  const envelope = record(task.result?.result);
  const data = record(envelope.data || envelope);
  const results = record(data.results);
  const datasets = "kruskal_wallis" in results || "success" in results && !("results" in results) ? [["统计结果", results] as const] : Object.entries(record(results.results));
  const image = typeof data.image === "string" ? data.image : "";
  return <>
    <PageHeader title="统计比较" subtitle="上传指标表，选择数值列与分组列，运行组间检验或生成箱线图。" />
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))", gap: 24, alignItems: "start" }}>
      <section style={{ background: "var(--bg-elevated)", border: "1px solid var(--separator)", borderRadius: 10, padding: 24 }}>
        <fieldset disabled={locked} style={{ border: 0, display: "grid", gap: 20, minWidth: 0 }}>
          <legend style={{ fontWeight: 600, marginBottom: 20 }}>1 · 准备数据</legend>
          <label className="field-label">所属项目<select className="select" value={project} onChange={event => { setProject(event.target.value); setFiles([]); setValue(""); setGroup(""); }}><option value="">请选择项目</option>{projects.status === "ready" && projects.data.projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          {projects.status === "error" && <p role="alert">项目加载失败：{projects.error}</p>}
          {projects.status === "ready" && !projects.data.projects.length && <Link to="/management/projects">先创建一个项目</Link>}
          <label className="field-label">上传指标表（可多选）<input aria-label="上传统计数据" type="file" accept=".csv,.tsv,.xlsx,.csv.gz" multiple disabled={!project || locked} onChange={event => { const incoming = Array.from(event.target.files || []); event.target.value = ""; void upload(incoming); }} /></label>
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>文件会上传至平台。每行是一条观测记录；多个文件分别分析，使用各文件共有的字段。</p>
          <ul style={{ listStyle: "none", padding: 0 }}>{files.map(file => <li key={file.id} style={{ display: "flex", gap: 12, justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--separator)" }}><span style={{ overflowWrap: "anywhere" }}>{file.name} · {file.row_count} 行</span><button className="btn btn-ghost" aria-label={`移除 ${file.name}`} onClick={() => setFiles(previous => previous.filter(item => item.id !== file.id))}>移除</button></li>)}</ul>
          <h3>2 · 设置比较</h3>
          <label className="field-label">分组列<select className="select" value={group} onChange={event => setGroup(event.target.value)}><option value="">请选择分组列</option>{columns.map(column => <option key={column}>{column}</option>)}</select></label>
          <label className="field-label">数值列<select className="select" value={value} onChange={event => setValue(event.target.value)}><option value="">请选择数值列</option>{columns.map(column => <option key={column}>{column}</option>)}</select></label>
          <label className="field-label">分析内容<select className="select" value={kind} onChange={event => setKind(event.target.value as typeof kind)}><option value="statistics">组间检验与描述统计</option><option value="boxplot">箱线图</option></select></label>
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>组间检验使用 Kruskal–Wallis；事后比较按现有分析服务执行。每个有效分组至少需要 2 条观测。</p>
          <button className="btn btn-primary" disabled={!files.length || !project || !group || !value || locked} onClick={run}>开始分析</button>
        </fieldset>
        {busy && <p role="status">正在上传或提交，请稍候…</p>}{error && <p role="alert" style={{ color: "var(--danger)", marginTop: 16 }}>{error}</p>}
      </section>
      <section style={{ minWidth: 0 }}>
        <h2>3 · 查看结果</h2>
        {!task.jobId && <p style={{ marginTop: 16, color: "var(--text-secondary)" }}>完成配置后开始分析，结果将在任务完成后显示。</p>}
        {task.jobId && <div style={{ margin: "16px 0" }}><p role="status">{statusLabels[task.status] || task.status}</p><Link to="/analysis/script-hub/jobs">查看任务列表</Link><p style={{ color: "var(--text-secondary)", fontSize: 12 }}>可保留当前页面地址，刷新后继续查看此任务。</p></div>}
        {task.error && <div role="alert"><p>{task.error}</p><button className="btn btn-secondary" onClick={task.retry}>重新读取任务</button></div>}
        {data.success === false && <p role="alert">{String(data.error || "分析失败")}</p>}
        {datasets.map(([name, raw]) => <StatisticalResult key={name} name={name} data={record(raw)} />)}
        {image && <div><img alt="分组箱线图" src={image.startsWith("data:image/") ? image : `data:image/png;base64,${image}`} style={{ width: "100%" }} /><a className="btn btn-secondary" download="boxplot.png" href={image.startsWith("data:image/") ? image : `data:image/png;base64,${image}`}>下载 PNG</a></div>}
        {!!task.result?.outputs?.length && <ResultViewer outputs={task.result.outputs} />}
      </section>
    </div>
  </>;
}

function StatisticalResult({ name, data }: { name: string; data: RecordValue }) {
  if (data.success === false) return <p role="alert">{name}：{String(data.error || "分析失败")}</p>;
  const kw = record(data.kruskal_wallis);
  return <article style={{ marginTop: 20, padding: 20, background: "var(--bg-elevated)", border: "1px solid var(--separator)", borderRadius: 8 }}><h3>{name}</h3>
    {kw.error ? <p role="alert">{String(kw.error)}</p> : <p>Kruskal–Wallis · H = {format(kw.statistic)} · p = {format(kw.p_value)}</p>}
    <ResultTable title="描述统计" rows={data.descriptive_stats} columns={{ group: "分组", n: "观测数", mean: "均值", median: "中位数", std: "标准差" }} />
    <ResultTable title="事后比较" rows={data.pairwise_comparisons} columns={{ group1: "分组 1", group2: "分组 2", p_value: "原始 p", p_value_corrected: "校正 p" }} />
  </article>;
}
function format(value: unknown) { return typeof value === "number" ? Number.isFinite(value) ? String(Number(value.toPrecision(5))) : "—" : value == null ? "—" : String(value); }
function ResultTable({ title, rows, columns }: { title: string; rows: unknown; columns: Record<string, string> }) {
  const records = Array.isArray(rows) ? rows.map(record) : [];
  const keys = Object.keys(columns);
  const csv = [Object.values(columns), ...records.map(row => keys.map(key => row[key] ?? ""))].map(row => row.map(value => `"${String(value).replace(/"/g, '""')}"`).join(",")).join("\r\n");
  return <div style={{ marginTop: 20 }}><h4>{title}</h4>{records.length ? <><a download={`${title}.csv`} href={`data:text/csv;charset=utf-8,${encodeURIComponent('\ufeff' + csv)}`}>下载 CSV</a><div style={{ overflowX: "auto" }}><table style={{ width: "100%", textAlign: "left", borderCollapse: "collapse" }}><thead><tr>{Object.values(columns).map(label => <th key={label} style={{ padding: 8 }}>{label}</th>)}</tr></thead><tbody>{records.map((row, index) => <tr key={index}>{keys.map(key => <td key={key} style={{ padding: 8, borderTop: "1px solid var(--separator)" }}>{format(row[key])}</td>)}</tr>)}</tbody></table></div></> : <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>本次分析未返回此项结果。</p>}</div>;
}
