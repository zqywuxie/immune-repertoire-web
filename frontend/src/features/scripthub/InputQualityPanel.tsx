import type { CSSProperties } from "react";
export interface InputQuality {
  inputs: Array<{ kind: string; label: string; sample_count: number; sample_column: string; status: string; duplicate_samples: string[]; missing_sample_count: number; missing_fields: Record<string, number>; row_count?: number; numeric_content?: { row_count: number; column_count: number; invalid_count: number; examples: string[] } }>;
  reference_label: string;
  alignments: Array<{ kind: string; label: string; matched_count: number; missing_count: number; extra_count: number; missing_samples: string[]; extra_samples: string[] }>;
  warnings: string[];
  errors: string[];
}

export function InputQualityPanel({ quality }: { quality: InputQuality }) {
  const pending = quality.inputs.some(input => input.status === "pending");
  return <section aria-label="输入质量与样本对应" style={{ display: "grid", gap: 12 }}>
    <h3 style={{ margin: 0 }}>输入质量与样本对应</h3>
    {quality.errors.map(message => {const waiting = pending && message.includes("后台校验"); return <p role={waiting ? "status" : "alert"} key={message} style={{ color: waiting ? "var(--text-secondary)" : "var(--danger)", margin: 0 }}>{waiting ? "输入数据正在后台校验，完成后将自动更新。" : message}</p>;})}
    <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(min(240px, 100%), 1fr))" }}>
      {quality.inputs.map(input => <article key={input.kind} style={{ padding: 16, border: "1px solid var(--separator)", borderRadius: "var(--radius-control)", background: "var(--bg-elevated)" }}>
        <strong>{input.label}</strong>
        <p style={{ margin: "8px 0" }}>{input.status === "pending" ? "正在后台校验，完成后自动更新" : input.status === "checked" ? "核验通过" : input.status === "invalid" ? "存在需要修正的问题" : "编号列或矩阵方向待确认"}</p>
        <div role="group" aria-label={`${input.label}数据量`} style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "10px 0" }}>
          {input.status !== "pending" && <span style={statStyle}>识别样本 {input.sample_count.toLocaleString("zh-CN")} 个</span>}
          {input.row_count !== undefined && <span style={statStyle}>数据行 {input.row_count.toLocaleString("zh-CN")} 行</span>}
          {input.numeric_content && <span style={statStyle}>数值区域 {input.numeric_content.row_count.toLocaleString("zh-CN")} 行 × {input.numeric_content.column_count.toLocaleString("zh-CN")} 列</span>}
        </div>
        {input.numeric_content && <div style={{ padding: 12, borderRadius: "var(--radius-control)", background: "var(--bg-inset)" }}>
          <div>数值核验：{input.numeric_content.invalid_count === 0 ? "全部通过" : `${input.numeric_content.invalid_count.toLocaleString("zh-CN")} 个单元格异常`}</div>
          {input.numeric_content.examples.length > 0 && <details style={{ marginTop: 6 }}>
            <summary>查看前五个异常位置</summary>
            <ul style={{ marginBottom: 0 }}>{input.numeric_content.examples.map((example, index) => <li key={`${example}-${index}`}>{example}</li>)}</ul>
          </details>}
        </div>}
        {input.sample_column && <p style={{ color: "var(--text-secondary)" }}>编号来源：{input.sample_column}</p>}
        {input.duplicate_samples.length > 0 && <details><summary>重复样本编号</summary><p style={{ overflowWrap: "anywhere" }}>{input.duplicate_samples.join("、")}</p></details>}
        {Object.keys(input.missing_fields).length > 0 && <details><summary>查看字段空值</summary><ul>{Object.entries(input.missing_fields).map(([field, count]) => <li key={field}>{field}：{count} 个空值</li>)}</ul></details>}
      </article>)}
    </div>
    {quality.alignments.length > 0 && <div style={{ overflowX: "auto" }}><table style={{ width: "100%", borderCollapse: "collapse" }}>
      <caption style={{ textAlign: "left", padding: "8px 0" }}>以{quality.reference_label}为参照核对样本编号</caption>
      <thead><tr>{["输入", "一致", "缺少", "多出", "差异明细"].map(label => <th scope="col" style={{ padding: 8, textAlign: "left" }} key={label}>{label}</th>)}</tr></thead>
      <tbody>{quality.alignments.map(item => <tr key={item.kind}>
        <td style={{ padding: 8 }}>{item.label}</td><td>{item.matched_count}</td><td>{item.missing_count}</td><td>{item.extra_count}</td>
        <td>{item.missing_count || item.extra_count ? <details><summary>查看编号</summary><p style={{ overflowWrap: "anywhere" }}>缺少：{item.missing_samples.join("、") || "无"}</p><p style={{ overflowWrap: "anywhere" }}>多出：{item.extra_samples.join("、") || "无"}</p><small>各显示前 50 个编号。</small></details> : "样本一致"}</td>
      </tr>)}</tbody>
    </table></div>}
    {quality.warnings.map(message => <p key={message} style={{ margin: 0, color: "var(--text-secondary)" }}>{message}</p>)}
  </section>;
}

const statStyle: CSSProperties = {
  padding: "4px 9px",
  borderRadius: "var(--radius-pill)",
  background: "var(--bg-inset)",
  color: "var(--text-secondary)",
  fontSize: "0.78rem",
  fontVariantNumeric: "tabular-nums",
};
