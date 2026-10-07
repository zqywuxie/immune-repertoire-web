import { useId } from "react";
import "./SampleIdMappingEditor.css";

export type SampleIdMapping = {source_sample: string; target_sample: string; source_batch?: string};

export function parseSampleIdMappings(text: string, batchScoped = false): {mappings: SampleIdMapping[]; error: string} {
  const mappings: SampleIdMapping[] = [];
  const sources = new Set<string>();
  const targets = new Set<string>();
  const lines = text.split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    if (!lines[index].trim()) continue;
    const cells = lines[index].split("\t").map(cell => cell.trim());
    if (cells.length !== (batchScoped ? 3 : 2) || cells.some(cell => !cell)) {
      return {mappings: [], error: batchScoped
        ? `第 ${index + 1} 行需要三列完整内容，请复制“原编号、统一编号、批次”三列，以制表符分隔。`
        : `第 ${index + 1} 行需要两列完整编号，请从表格复制“原编号、统一编号”两列，以制表符分隔。`};
    }
    const [source, target, batch = ""] = cells;
    const sourceKey = JSON.stringify([batch, source]);
    const targetKey = JSON.stringify([batch, target]);
    if (sources.has(sourceKey) || targets.has(targetKey)) {
      return {mappings: [], error: `第 ${index + 1} 行${batchScoped ? "同一批次中的" : ""}编号重复，每个原编号和统一编号只能填写一次。`};
    }
    sources.add(sourceKey);
    targets.add(targetKey);
    mappings.push({source_sample: source, target_sample: target, ...(batchScoped ? {source_batch: batch} : {})});
  }
  return {mappings, error: ""};
}

export function SampleIdMappingEditor({value, mappings, error, disabled, onChange, batchScoped = false}: {
  value: string; mappings: SampleIdMapping[]; error: string; disabled: boolean; onChange: (value: string) => void; batchScoped?: boolean;
}) {
  const id = useId();
  return <div className="sample-id-mapping">
    <label className="field-label" htmlFor={id}>样本编号对应（可选）</label>
    <p id={`${id}-help`} className="sample-id-mapping__help">
      {batchScoped ? "从表格复制三列：第一列原编号，第二列统一编号，第三列原批次，每行一条。对应按批次分别核对，不同批次可保留同名样本。" : "从表格复制两列：第一列原编号，第二列统一编号，每行一条。可用于对齐克隆序列文件的样本名或其他输入的样本编号。"}
      留空或未填写的样本保留原编号。
    </p>
    <textarea id={id} className="input sample-id-mapping__textarea" value={value} rows={4} disabled={disabled} aria-invalid={Boolean(error)}
      aria-describedby={`${id}-help${error ? ` ${id}-error` : ""}`} placeholder={batchScoped ? "原编号\t统一编号\t批次\nRNA-001\t001\t批次一" : "原编号\t统一编号\nRNA-001\t001"}
      onChange={event => onChange(event.target.value)} />
    {error ? <p id={`${id}-error`} role="alert" className="sample-id-mapping__error">{error}</p> : mappings.length > 0 ? <>
      <p style={{margin: 0, fontSize: "0.85rem"}}>已填写 {mappings.length.toLocaleString("zh-CN")} 条对应，保存时将核对{batchScoped ? "原批次和" : ""}原编号存在且{batchScoped ? "同一批次内" : "统一后"}没有重名。</p>
      <div className="input-mapping-table-wrap"><table className="input-mapping-table">
        <caption>编号对应预览{mappings.length > 10 ? "（前十条）" : ""}</caption>
        <thead><tr><th scope="col">原编号</th><th scope="col">统一编号</th>{batchScoped && <th scope="col">批次</th>}</tr></thead>
        <tbody>{mappings.slice(0, 10).map(item => <tr key={JSON.stringify([item.source_batch, item.source_sample])}><td>{item.source_sample}</td><td>{item.target_sample}</td>{batchScoped && <td>{item.source_batch}</td>}</tr>)}</tbody>
      </table></div>
    </> : null}
  </div>;
}
