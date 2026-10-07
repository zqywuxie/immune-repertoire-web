import { useEffect, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  CommonRunFields,
  GroupFieldSelect,
  GroupFieldMultiSelect,
  GroupOrderEditor,
  GroupValueSamplePicker,
  GroupSpecSelect,
  ModuleShell,
  RangeFields,
  Section,
  gridStyle,
  setFieldValue,
  stringList,
  useSyncedDefaults,
  withDefaults,
} from "./shared";

type ProfileInspectResponse = {
  success: boolean;
  suggested_grouping_begin?: string;
  suggested_grouping_over?: string;
  suggested_param_begin?: string;
  suggested_param_over?: string;
  csr_measures?: Record<string, string[]>;
};

function discoverCompositionColumns(columns: string[], measure: string) {
  const chainAliases: Record<string, string[]> = {
    TRA: ["TRA_Percent", "TRA_percent_reads"],
    TRB: ["TRB_Percent", "TRB_percent_reads"],
    TRD: ["TRD_Percent", "TRD_percent_reads"],
    TRG: ["TRG_Percent", "TRG_percent_reads"],
    IGH: ["IGH_Percent", "IGH_percent_reads"],
    IGK: ["IGK_Percent", "IGK_percent_reads"],
    IGL: ["IGL_Percent", "IGL_percent_reads"],
  };
  const chains = Object.values(chainAliases).map((aliases) => aliases.find((column) => columns.includes(column))).filter((column): column is string => Boolean(column));
  const pattern = new RegExp(`^((?:IGH[A-Z0-9]+)(?:_IGH[A-Z0-9]+)*)_percent_by_${measure}$`, "i");
  const tokens = columns.map((column) => column.match(pattern)?.[1]).filter((token): token is string => Boolean(token));
  const canonical = ["IGHM", "IGHD", "IGHA", "IGHA1", "IGHA2", "IGHG12", "IGHG34", "IGHG3", "IGHG4", "IGHGP", "IGHE"];
  const ordered = [...canonical.filter((token) => tokens.includes(token)), ...[...new Set(tokens)].filter((token) => !canonical.includes(token)).sort()];
  return { chains, subclass_columns: ordered.map((token) => columns.find((column) => pattern.test(column) && column.startsWith(token)) || `${token}_percent_by_${measure}`) };
}

export function ProfileConfig({ sourceContext, groupSpecs, loadingSpecs, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    pvalue_threshold: 0.05,
    grouptype_fields: [],
  });
  const [inspectNote, setInspectNote] = useState("");
  const compositionMode = current.analysis_type === "composition";
  const csrMode = current.analysis_type === "csr";
  const selectedGroup = String(current.group_column || stringList(current.grouptype_fields)[0] || "");
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    if (!sourceContext?.profilePath) return;
    let cancelled = false;
    inspectScriptHubModule<ProfileInspectResponse>("profile", {
      project_id: sourceContext.projectId,
      asset_set: sourceContext.assetSetId,
      profile_path: sourceContext.profilePath,
      datapoint_path: sourceContext.profilePath,
      base_path: sourceContext.pepPaths?.[0],
    })
      .then((data) => {
        if (cancelled) return;
        const suggested = {
          param_begin: data.suggested_param_begin,
          param_over: data.suggested_param_over,
        };
        const next = Object.fromEntries(Object.entries(suggested).filter(([, item]) => item));
        if (!compositionMode && !csrMode && Object.keys(next).length && !value.param_begin && !value.param_over) {
          onChange({ ...current, ...next });
        }
        setInspectNote("已读取指标范围，请确认分组列和要比较的指标。");
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "读取样本指标表失败");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.profilePath, compositionMode, csrMode]);

  if (csrMode) {
    const measures = Object.keys(discoverCsrMeasures(sourceContext?.profileFields || []));
    const selectedMeasure = String(current.csr_measure || "auto");
    return (
      <ModuleShell
        title="免疫球蛋白类别转换矩阵"
        detail="根据样本指标表中的 CSR 指标，比较各组类别转换关系，并输出原始中位数、组间效应及多重检验结果。"
        sourceContext={sourceContext}
      >
        {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
        <Section title="分组与统计口径">
          <div style={gridStyle}>
            <GroupFieldSelect
              label="分组列（必选）"
              value={selectedGroup}
              sourceContext={sourceContext}
              onChange={(next) => onChange({ ...current, group_column: next, grouptype_fields: next ? [next] : [] })}
              emptyLabel="未检测到分组列，请检查样本指标表"
            />
            <GroupOrderEditor
              selectedFields={selectedGroup ? [selectedGroup] : []}
              sourceContext={sourceContext}
              value={current.group_order}
              onChange={(next) => setField("group_order", next)}
            />
            <div style={{ display: "grid", gap: 6 }}>
              <label htmlFor="profile-csr-measure" style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>CSR 指标口径</label>
              <select id="profile-csr-measure" className="input" value={selectedMeasure} onChange={(event) => setField("csr_measure", event.target.value)}>
                <option value="auto">自动选择（CSR_ratio 优先）</option>
                {measures.includes("CSR_ratio") && <option value="CSR_ratio">CSR_ratio</option>}
                {measures.includes("CSR1") && <option value="CSR1">CSR1</option>}
                {measures.includes("CSR0") && <option value="CSR0">CSR0</option>}
              </select>
              <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>纯数值列的空值按 0 处理；混合文本列中无法转换的值会跳过。每组至少 2 个有效样本才进行检验。</span>
            </div>
            <GroupValueSamplePicker value={{ ...current, grouptype_fields: selectedGroup ? [selectedGroup] : [] }} setField={setField} sourceContext={sourceContext} fields={selectedGroup ? [selectedGroup] : []} />
          </div>
          <div style={{ marginTop: 12, padding: 12, borderRadius: 8, background: "var(--bg-inset)", color: "var(--text-secondary)", fontSize: "0.82rem" }}>
            <div>已检测统计口径：{measures.length ? measures.join("、") : "没有 CSR_ratio、CSR1 或 CSR0 列"}</div>
            <div style={{ marginTop: 4 }}>组间采用双侧 Mann–Whitney 检验并按每组比较执行 BH 校正；多组总体差异另输出 Kruskal 检验。</div>
          </div>
        </Section>
        <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
      </ModuleShell>
    );
  }

  if (compositionMode) {
    const measure = String(current.subclass_measure || "reads");
    const detected = discoverCompositionColumns(sourceContext?.profileFields || [], measure);
    return (
      <ModuleShell
        title="受体链与免疫球蛋白亚类构成"
        detail="按样本展示各构成分量。缺失分量按 0 处理，再将每个样本的选中分量闭合到 100%。"
        sourceContext={sourceContext}
      >
        {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
        <Section title="分组与构成口径">
          <div style={gridStyle}>
            <GroupFieldSelect
              label="分组列（必选）"
              value={selectedGroup}
              sourceContext={sourceContext}
              onChange={(next) => onChange({ ...current, group_column: next, grouptype_fields: next ? [next] : [] })}
              emptyLabel="未检测到分组列，请检查样本指标表"
            />
            <GroupOrderEditor
              selectedFields={selectedGroup ? [selectedGroup] : []}
              sourceContext={sourceContext}
              value={current.group_order}
              onChange={(next) => setField("group_order", next)}
            />
            <div style={{ display: "grid", gap: 6 }}>
              <label htmlFor="profile-composition-measure" style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>亚类百分比口径</label>
              <select id="profile-composition-measure" className="input" value={measure} onChange={(event) => setField("subclass_measure", event.target.value)}>
                <option value="reads">按测序读段</option>
                <option value="clone">按克隆数</option>
              </select>
              <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>受体链图使用读段比例；此选项只切换免疫球蛋白亚类图。</span>
            </div>
            <GroupValueSamplePicker value={{ ...current, grouptype_fields: selectedGroup ? [selectedGroup] : [] }} setField={setField} sourceContext={sourceContext} fields={selectedGroup ? [selectedGroup] : []} />
          </div>
          <div style={{ marginTop: 12, padding: 12, borderRadius: 8, background: "var(--bg-inset)", color: "var(--text-secondary)", fontSize: "0.82rem" }}>
            <div>可生成受体链图：{(detected.chains || []).length ? (detected.chains || []).join("、") : "样本指标表中没有链比例列"}</div>
            <div style={{ marginTop: 4 }}>可生成亚类图：{(detected.subclass_columns || []).length ? (detected.subclass_columns || []).map((column) => column.replace(/_percent_by_(reads|clone)$/i, "").replace(/^IGH/, "Ig")).join("、") : `没有按 ${measure === "reads" ? "测序读段" : "克隆数"} 统计的亚类比例列`}</div>
          </div>
        </Section>
        <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
      </ModuleShell>
    );
  }

  return (
    <ModuleShell
      title="指标分组箱线图"
      detail="选择分组列与指标范围，按样本比较组间分布，并输出箱线图和统计表。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="分组与分析指标">
        <div style={gridStyle}>
          <GroupFieldMultiSelect
            label="分组列（必选）"
            selected={stringList(current.grouptype_fields)}
            sourceContext={sourceContext}
            onChange={(next) => setField("grouptype_fields", next)}
            emptyLabel="未检测到分组列，请返回检查 样本指标表"
          />
          <GroupOrderEditor
            selectedFields={stringList(current.grouptype_fields)}
            sourceContext={sourceContext}
            value={current.group_order}
            onChange={(next) => setField("group_order", next)}
          />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={stringList(current.grouptype_fields)} />
          <RangeFields value={current} setField={setField} sourceContext={sourceContext} parameterLabels />
          <GroupSpecSelect value={current} setField={setField} groupSpecs={groupSpecs} loadingSpecs={loadingSpecs} />
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}

function discoverCsrMeasures(columns: string[]) {
  const result: Record<string, string[]> = {};
  const pattern = /^[A-Za-z0-9_]+-[A-Za-z0-9_]+_(CSR_ratio|CSR0|CSR1)$/i;
  for (const column of columns) {
    const match = column.match(pattern);
    if (!match) continue;
    const measure = match[1].toUpperCase() === "CSR_RATIO" ? "CSR_ratio" : match[1].toUpperCase();
    (result[measure] ||= []).push(column);
  }
  return result;
}
