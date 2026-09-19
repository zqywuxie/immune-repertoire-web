import { useEffect, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  ColumnSelect,
  CommonRunFields,
  Field,
  GroupFieldMultiSelect,
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
    pathology_values: [],
    contained_pathology: false,
  });
  const [inspectNote, setInspectNote] = useState<string>("");
  const mapping = (current.field_mapping as Record<string, unknown> | undefined) || {};
  const pepColumns = sourceContext?.pepColumns || [];
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    if (!sourceContext?.pepPaths?.length) return;
    let cancelled = false;
    inspectScriptHubModule<DbInspectResponse>("db-alignment", {
      base_path: sourceContext.pepPaths[0],
      pep_paths: sourceContext.pepPaths,
      profile_path: sourceContext.profilePath,
      field_mapping: current.field_mapping,
    })
      .then((data) => {
        if (cancelled) return;
        const suggested = data.resolved_field_mapping || data.suggested_field_mapping;
        if (suggested && !value.field_mapping) {
          onChange({ ...current, field_mapping: suggested });
        }
        if (data.preview_columns?.length) {
          setInspectNote(`Detected ${data.preview_columns.length} 列数据库比对预览数据。`);
        }
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "数据库比对输入检查失败");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.pepPaths?.join("|"), sourceContext?.profilePath]);

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
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={stringList(current.categories)} />
          <Field label="病理分组值">
            <input value={listInput(current.pathology_values)} onChange={(event) => setField("pathology_values", splitList(event.target.value))} placeholder="可选，填写筛选值" style={inputStyle} />
          </Field>
          <SwitchField label="包含病理分组" checked={Boolean(current.contained_pathology)} onChange={(checked) => setField("contained_pathology", checked)} />
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
      <Section title="克隆序列表字段映射">
        <div style={gridStyle}>
          <ColumnSelect label="CDR3 序列列" value={stringValue(mapping.cdr3_column)} options={pepColumns} onChange={(next) => setField("field_mapping", { ...mapping, cdr3_column: next })} emptyLabel="未识别到克隆序列表的列" />
          <ColumnSelect label="拷贝数列" value={stringValue(mapping.copy_column)} options={pepColumns} onChange={(next) => setField("field_mapping", { ...mapping, copy_column: next })} emptyLabel="未识别到克隆序列表的列" />
        </div>
      </Section>
    </ModuleShell>
  );
}
