import "./SourceSelection.css";

/** Open saved source tasks without replacing the analysis configuration. */
export function SourceTaskLink({jobId, projectId, assetSet}: {jobId?: string; projectId?: string; assetSet?: string}) {
  if (!jobId) return null;
  const query = new URLSearchParams({job: jobId});
  if (projectId) query.set("project", projectId);
  if (assetSet) query.set("asset_set", assetSet);
  return <a className="source-task-link" href={"/analysis/script-hub/jobs?" + query} target="_blank" rel="noreferrer"
    aria-label={"查看来源任务 " + jobId}>查看来源任务 ↗</a>;
}

/** Source catalogs store UTC; legacy ISO values may omit their timezone. */
export function formatSourceTime(value?: string) {
  if (!value) return "未记录时间";
  const original = value.trim();
  const iso = original.replace(" ", "T");
  const timestamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(iso) ? iso + "Z" : iso;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", {hour12: false, timeZoneName: "short"});
}
