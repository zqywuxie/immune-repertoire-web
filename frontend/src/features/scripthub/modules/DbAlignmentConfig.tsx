import { useEffect, useRef, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  ColumnSelect,
  CommonRunFields,
  Field,
  GroupFieldMultiSelect,
  GroupFieldSelect,
  GroupValueSamplePicker,
  ModuleShell,
  Section,
  SwitchField,
  gridStyle,
  guessColumn,
  inputStyle,
  listInput,
  setFieldValue,
  splitList,
  stringList,
  stringValue,
  useSyncedDefaults,
  withDefaults,
} from "./shared";

type DbInspectResponse = {
  success: boolean;
  preview_columns?: string[];
  suggested_field_mapping?: Record<string, string>;
  resolved_field_mapping?: Record<string, string>;
  reference_sources?: Array<{ name: string; available: boolean; path?: string }>;
};

export function DbAlignmentConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    pvalue_threshold: 0.05,
    field_mapping: {
      cdr3_column: guessColumn(sourceContext?.pepColumns || [], ["cdr3", "junction_aa", "aaSeqCDR3", "amino"]),
      copy_column: guessColumn(sourceContext?.pepColumns || [], ["copy", "count", "cloneCount", "frequency", "freq"]),
    },
    categories: [],
    batch_field: "",
    pathology_values: [],
    contained_pathology: false,
  });
  const [inspectNote, setInspectNote] = useState<string>("");
  const [inspectColumns, setInspectColumns] = useState<string[]>([]);
  const mapping = (current.field_mapping as Record<string, unknown> | undefined) || {};
  const pepColumns = inspectColumns.length ? inspectColumns : sourceContext?.pepColumns || [];
  const latest = useRef({ value, current, onChange });
  latest.current = { value, current, onChange };
  const setField = (key: string, next: unknown) => {
    if (key === "batch_field") onChange({ ...current, batch_field: next, selected_samples_by_group: undefined,
      group_sample_identity: next ? "batch_sample" : "sample" });
    else if (key === "selected_samples_by_group") onChange({ ...current, selected_samples_by_group: next,
      group_sample_identity: current.batch_field ? "batch_sample" : "sample" });
    else setFieldValue(current, onChange, key, next);
  };
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    setInspectNote("");
    setInspectColumns([]);
    if (!sourceContext?.pepPaths?.length) return;
    let cancelled = false;
    setInspectNote("正在检查数据库比对输入…");
    inspectScriptHubModule<DbInspectResponse>("db-alignment", {
      base_path: sourceContext.pepPaths[0],
      pep_paths: sourceContext.pepPaths,
      profile_path: sourceContext.profilePath,
      field_mapping: current.field_mapping,
      batch_field: current.batch_field || undefined,
    })
      .then((data) => {
        if (cancelled) return;
        setInspectColumns(data.preview_columns || []);
        const suggested = data.resolved_field_mapping || data.suggested_field_mapping;
        if (suggested) {
          const saved = (latest.current.current.field_mapping as Record<string, unknown> | undefined) || {};
          const filled = { ...saved };
          for (const key of ["cdr3_column", "copy_column"]) if (!saved[key] && suggested[key]) filled[key] = suggested[key];
          if (Object.keys(filled).some((key) => filled[key] !== saved[key])) {
            latest.current.onChange({ ...latest.current.current, field_mapping: filled });
          }
        }
        const notes: string[] = [];
        if (data.preview_columns?.length) notes.push(`已识别 ${data.preview_columns.length} 列克隆数据。`);
        const missingReferences = (data.reference_sources || []).filter((source) => !source.available);
        if (missingReferences.some((source) => source.name === "IEDB")) {
          notes.push("未检测到 IEDB 参考表；IEDB 命中暂不可用，Combined 指标仅合并 VDJdb 与 McPAS-TCR。");
        }
        const missingRequired = missingReferences.filter((source) => source.name !== "IEDB");
        if (missingRequired.length) {
          notes.push(`必需参考库缺失：${missingRequired.map((source) => source.name).join("、")}，提交分析会失败。`);
        }
        setInspectNote(notes.join(" "));
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "数据库比对输入检查失败");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.pepPaths?.join("|"), sourceContext?.profilePath, current.batch_field]);

  return (
    <ModuleShell
      title="数据库比对"
      detail="从已识别的数据列中选择克隆序列、拷贝数和样本分类。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="样本指标注释">
        <div style={gridStyle}>
          <GroupFieldMultiSelect label="样本指标分类" selected={stringList(current.categories)} sourceContext={sourceContext} onChange={(next) => setField("categories", next)} emptyLabel="未识别到样本指标表的分组列" />
          <GroupFieldSelect label="批次字段（可选）" value={stringValue(current.batch_field)} sourceContext={sourceContext}
            optional emptyLabel="未选择批次字段" onChange={(next) => setField("batch_field", next || undefined)} />
          <GroupValueSamplePicker batchField={stringValue(current.batch_field)} value={current} setField={setField} sourceContext={sourceContext} fields={stringList(current.categories)} />
          <Field label="病理分组值">
            <input value={listInput(current.pathology_values)} onChange={(event) => setField("pathology_values", splitList(event.target.value))} placeholder="可选，填写筛选值" style={inputStyle} />
          </Field>
          <SwitchField label="包含病理分组" checked={Boolean(current.contained_pathology)} onChange={(checked) => setField("contained_pathology", checked)} />
        </div>
      </Section>
      <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.7 }}>
        不同批次的同名样本可分别选择；克隆文件所在批次目录名需与所选字段值一致。组间比较沿用 p 值 0.05 的判定。
      </div>
      <CommonRunFields showPvalue={false} value={current} setField={setField} sourceContext={sourceContext} />
      <Section title="克隆序列表字段映射">
        <div style={gridStyle}>
          <ColumnSelect label="CDR3 序列列" value={stringValue(mapping.cdr3_column)} options={pepColumns} onChange={(next) => setField("field_mapping", { ...mapping, cdr3_column: next })} emptyLabel="未识别到克隆序列表的列" />
          <ColumnSelect label="拷贝数列" value={stringValue(mapping.copy_column)} options={pepColumns} onChange={(next) => setField("field_mapping", { ...mapping, copy_column: next })} emptyLabel="未识别到克隆序列表的列" />
        </div>
      </Section>
    </ModuleShell>
  );
}
