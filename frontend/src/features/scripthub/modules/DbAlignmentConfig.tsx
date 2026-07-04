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
          setInspectNote(`Detected ${data.preview_columns.length} columns from DB alignment preview file.`);
        }
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "DB alignment inspect failed");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.pepPaths?.join("|"), sourceContext?.profilePath]);

  return (
    <ModuleShell
      title="DB Alignment"
      detail="PEP 字段映射和 Profile 分类来自检测列；CDR3/copy 不允许手输。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="Profile Annotation">
        <div style={gridStyle}>
          <GroupFieldMultiSelect label="Profile Categories" selected={stringList(current.categories)} sourceContext={sourceContext} onChange={(next) => setField("categories", next)} emptyLabel="No Profile group fields detected" />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={stringList(current.categories)} />
          <Field label="Pathology Values">
            <input value={listInput(current.pathology_values)} onChange={(event) => setField("pathology_values", splitList(event.target.value))} placeholder="optional value filter" style={inputStyle} />
          </Field>
          <SwitchField label="Contained Pathology" checked={Boolean(current.contained_pathology)} onChange={(checked) => setField("contained_pathology", checked)} />
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
      <Section title="PEP Field Mapping">
        <div style={gridStyle}>
          <ColumnSelect label="CDR3 Column" value={stringValue(mapping.cdr3_column)} options={pepColumns} onChange={(next) => setField("field_mapping", { ...mapping, cdr3_column: next })} emptyLabel="No PEP columns detected" />
          <ColumnSelect label="Copy Column" value={stringValue(mapping.copy_column)} options={pepColumns} onChange={(next) => setField("field_mapping", { ...mapping, copy_column: next })} emptyLabel="No PEP columns detected" />
        </div>
      </Section>
    </ModuleShell>
  );
}
