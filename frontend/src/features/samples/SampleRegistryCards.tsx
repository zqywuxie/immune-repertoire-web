import { Pencil } from "lucide-react";
import type { SampleRecord } from "../../shared/api/samples";
import { Skeleton } from "../../shared/components/Skeleton";
import { healthyLabel, pairedLabel, speciesLabel, registrationSource, manuallyMaintainedFields, sampleFieldLabels } from "./sampleDisplay";

export function SampleRegistryCards({ samples, loading, onEdit, selectedIds, onToggle }: {
  samples: SampleRecord[]; loading: boolean; onEdit: (sample: SampleRecord) => void;
  selectedIds?: Set<string>; onToggle?: (sample: SampleRecord) => void;
}) {
  if (loading) return <div role="status" aria-label="正在读取样本"><Skeleton height="150px" /></div>;
  if (!samples.length) return <p className="data-table-empty">未找到样本，请调整筛选条件。</p>;
  return <div className="data-mobile-records" aria-label="样本记录">{samples.map(sample => {
    const dataset = String(sample.extra_metadata.asset_set || "未标记来源");
    const manual = manuallyMaintainedFields(sample.extra_metadata);
    const facts = [["链类型", sample.chain_flag || "未填写"], ["健康状态", healthyLabel(sample.is_healthy)],
      ["序列编号", sample.sequence_id || "未填写"], ["双端测序", pairedLabel(sample.is_pe)],
      ["所属机构", sample.institution || "未填写"], ["纳入方法", sample.contain_method || "未填写"],
      ["同型标签", sample.iso_tag || "未填写"]];
    return <article className="data-mobile-record" key={sample.id} aria-label={`样本 ${sample.sample_id || "未填写编号"} · ${dataset}`}>
      <div className="data-mobile-record-heading"><div><code>{sample.sample_id || "未填写编号"}</code><h3>{sample.sample_name}</h3></div>
        <button className="btn btn-secondary" aria-label={`编辑样本 ${sample.sample_id || "未填写编号"}（${dataset}）`} onClick={() => onEdit(sample)}><Pencil size={15} />编辑</button></div>
      {onToggle && <label className="sample-batch-select"><input type="checkbox" aria-label={`选择登记 ${sample.sample_id || sample.sample_name}（${dataset}）`} checked={selectedIds?.has(sample.id) || false} onChange={() => onToggle(sample)}/>选择此登记</label>}
      <p className="data-mobile-record-scope">{sample.project_name || "未填写项目名称"} · 数据集：{dataset}</p>
      <p className="data-mobile-record-summary">{speciesLabel(sample.spices)} · {sample.illness || "疾病未填写"}</p>
      <small className="data-registration-source">{registrationSource(sample.extra_metadata)}</small>
      <details className="data-mobile-record-details"><summary>登记详情{manual.length > 0 ? ` · 人工维护 ${manual.length} 项` : ""}</summary>
        <dl>{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
        {manual.length > 0 && <p className="data-muted">人工维护：{manual.map(field => sampleFieldLabels[field] || "其他补充字段").join("、")}</p>}
      </details>
    </article>;
  })}</div>;
}
