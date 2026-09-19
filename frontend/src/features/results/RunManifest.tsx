import type { JobResultsResponse } from '../../shared/api/jobs';
export function RunManifest({ results }: { results: JobResultsResponse[] }) {
  const manifest = { schema_version: 1, exported_at: new Date().toISOString(), runs: results.map(result => ({ job: result.job, status: result.status, outputs: result.outputs, result: result.result })) };
  return <details style={{marginBlock:16}}><summary>分析记录与复现参数</summary><p>保存任务参数、输入标识、结果及输出文件清单，便于核对分组和复现分析。</p><a className="btn btn-secondary" download="analysis-record.json" href={'data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(manifest,null,2))}>下载分析记录 JSON</a></details>;
}
