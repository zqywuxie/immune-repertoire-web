import { useEffect } from "react";
import type { GroupSpec } from "../../../shared/api/groupSpecs";
import type { ScriptHubSourceContext } from "./index";

type Props = {
  projectId: string;
  module: string;
  sourceContext?: ScriptHubSourceContext;
  groupSpecs: GroupSpec[];
  loadingSpecs: boolean;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
};

const CHAIN_OPTIONS = ["TRA", "TRB", "TRG", "TRD", "IGH", "IGK", "IGL"];
const PEP_OPTIONAL_STEPS = [
  { key: "2", label: "PEP shared / usage" },
  { key: "5", label: "Differential heatmaps" },
  { key: "6", label: "CDR3 category tables" },
];

export function LegacyScriptHubForm({
  module,
  sourceContext,
  groupSpecs,
  loadingSpecs,
  value,
  onChange,
}: Props) {
  const setField = (key: string, next: unknown) => onChange({ ...defaultConfig(module, value), [key]: next });
  const current = applySourceDefaults(module, defaultConfig(module, value), value, sourceContext);
  const currentSignature = JSON.stringify(current);
  const valueSignature = JSON.stringify(value);

  useEffect(() => {
    if (currentSignature !== valueSignature) {
      onChange(current);
    }
  }, [currentSignature, valueSignature, current, onChange]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
      <ModuleNotice module={module} />
      <SourceSummary sourceContext={sourceContext} />
      <CommonFields value={current} setField={setField} />

      {module === "db-alignment" && <DbAlignmentFields value={current} setField={setField} sourceContext={sourceContext} />}
      {(module === "profile" || module === "boxplot") && (
        <ProfileBoxplotFields value={current} setField={setField} sourceContext={sourceContext} groupSpecs={groupSpecs} loadingSpecs={loadingSpecs} />
      )}
      {module === "pep-analysis" && <PepAnalysisFields value={current} setField={setField} sourceContext={sourceContext} />}
      {module === "pgen-analysis" && <PgenFields value={current} setField={setField} sourceContext={sourceContext} />}
      {module === "topclone" && <TopCloneFields value={current} setField={setField} sourceContext={sourceContext} />}
      {module === "umap" && <UmapFields value={current} setField={setField} sourceContext={sourceContext} />}
      {module === "volcano" && <VolcanoFields value={current} setField={setField} />}
      {module === "go-kegg-enrichment" && <GoKeggFields value={current} setField={setField} />}
      {module === "umapin" && <UmapinFields value={current} setField={setField} sourceContext={sourceContext} />}
      {module === "ml-analysis" && <MlFields value={current} setField={setField} sourceContext={sourceContext} />}
      {module === "mait-nkt" && <MaitNktFields value={current} setField={setField} sourceContext={sourceContext} />}
      {module === "charts" && <ChartsNotice />}
    </div>
  );
}

function defaultConfig(module: string, value: Record<string, unknown>) {
  const defaults: Record<string, unknown> = {
    output_name: "",
    pvalue_threshold: 0.05,
  };
  if (["pep-analysis", "pgen-analysis", "topclone"].includes(module)) {
    defaults.selected_chains = ["TRA", "TRB"];
  }
  if (module === "pep-analysis") {
    defaults.group_fields = [];
    defaults.min_sample_threshold = 3;
    defaults.optional_steps = ["2", "5", "6"];
  }
  if (module === "pgen-analysis") {
    defaults.species = "human";
    defaults.sample_col = "sample";
    defaults.distribution_category_col = "";
  }
  if (module === "topclone") {
    defaults.mode = "trace";
    defaults.top_n = 10;
  }
  if (module === "umap") {
    defaults.n_neighbors = 6;
    defaults.min_dist = 0.01;
  }
  if (module === "volcano") {
    defaults.input_mode = "expression";
    defaults.group_prefix = "tpm_";
    defaults.logfc_cutoff = 1;
  }
  if (module === "go-kegg-enrichment") {
    defaults.group_prefix = "tpm_";
    defaults.logfc_cutoff = 1;
    defaults.enrich_pvalue_cutoff = 0.05;
    defaults.p_adjust_method = "none";
    defaults.show_category = 20;
    defaults.simplify_go = true;
    defaults.do_gsea = true;
  }
  if (module === "umapin") {
    defaults.category_col = "Category";
    defaults.n_neighbors = 6;
    defaults.min_dist = 0.01;
    defaults.do_fdr = false;
  }
  if (module === "ml-analysis") {
    defaults.mode = "profile";
    defaults.sample_col = "Sample";
    defaults.custom_threshold = 0.003;
    defaults.cv_splits = 3;
    defaults.roc_cv_splits = 7;
  }
  if (module === "mait-nkt") {
    defaults.tra_source = "upload";
  }
  return { ...defaults, ...value };
}

function applySourceDefaults(
  module: string,
  current: Record<string, unknown>,
  rawValue: Record<string, unknown>,
  sourceContext?: ScriptHubSourceContext,
) {
  const next = { ...current };
  const detectedChains = sourceContext?.chains?.length ? sourceContext.chains : [];
  if (["pep-analysis", "pgen-analysis", "topclone"].includes(module) && !Array.isArray(rawValue.selected_chains)) {
    next.selected_chains = detectedChains.length ? detectedChains : next.selected_chains;
  }
  if (module === "db-alignment" && !rawValue.field_mapping && sourceContext?.pepColumns?.length) {
    next.field_mapping = {
      cdr3_column: guessColumn(sourceContext.pepColumns, ["cdr3", "junction_aa", "aaSeqCDR3", "amino"]),
      copy_column: guessColumn(sourceContext.pepColumns, ["copy", "count", "cloneCount", "frequency", "freq"]),
    };
  }
  if (["pgen-analysis", "ml-analysis"].includes(module) && !rawValue.sample_col && sourceContext?.profileFields?.length) {
    next.sample_col = guessColumn(sourceContext.profileFields, ["sample", "sample_id", "sample_name"]) || next.sample_col;
  }
  if (module === "ml-analysis" && !rawValue.label_col && detectedGroupFields(sourceContext).length) {
    next.label_col = detectedGroupFields(sourceContext)[0];
  }
  return next;
}

function ModuleNotice({ module }: { module: string }) {
  const text: Record<string, string> = {
    "db-alignment": "需要 PEP 目录和 CDR3/copy 字段映射；Profile 分组字段用于结果注释。",
    profile: "参考老版 Profile 分析：选择分组区间与参数区间，生成分组箱线图和统计检验。",
    "pep-analysis": "参考 Pep_260213：PEP 共享矩阵、V/J/VJ usage、分组热图与 CDR3 分类。",
    "pgen-analysis": "参考 Pgen_260213 / SoNNia：按样本与链计算 Pgen、Q、Ppost。",
    topclone: "TopClone 支持 trace 与 per_sample 两种模式；trace 模式需要 Profile 分组。",
    umap: "基于 Profile 显著性预筛选后的 UMAP 投影。",
    volcano: "支持表达矩阵模式或 VJ usage 缓存模式。",
    "go-kegg-enrichment": "基于表达矩阵做差异分析、ORA 和可选 GSEA。",
    umapin: "基于 VJ usage 汇总表做 UMAPin 降维。",
    "ml-analysis": "参考 ML_260526 随机森林流程，支持 Profile 特征或 VJ usage 特征。",
    "mait-nkt": "基于 TRA CDR3 宽表和 Profile 分组计算 MAIT/NKT 丰度。",
    charts: "综合图表目前需要后续接入独立执行桥或新 jobs 模块。",
  };
  return (
    <div style={noticeStyle}>
      <strong style={{ color: "var(--text-primary)" }}>Module contract</strong>
      <span>{text[module] || "Configure the selected Script Hub module."}</span>
    </div>
  );
}

function SourceSummary({ sourceContext }: { sourceContext?: ScriptHubSourceContext }) {
  if (!sourceContext) return null;
  return (
    <Section title="Detected Sources">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "var(--spacing-sm)" }}>
        <SourceLine label="Asset Set" value={sourceContext.assetSetId || "Manual selection"} />
        <SourceLine label="PEP Paths" value={`${sourceContext.pepPaths?.length || 0} selected`} title={(sourceContext.pepPaths || []).join("\n")} />
        <SourceLine label="Profile" value={sourceContext.profilePath || "Not selected"} />
        <SourceLine label="Transcriptome" value={sourceContext.transcriptomePath || "Not selected"} />
      </div>
    </Section>
  );
}

function SourceLine({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div style={{ minWidth: 0, padding: "8px 10px", borderRadius: "var(--radius-control)", background: "var(--bg-inset)" }}>
      <div style={{ fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "3px" }}>{label}</div>
      <div
        title={title || value}
        style={{ fontSize: "0.8rem", color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
      >
        {value}
      </div>
    </div>
  );
}

function CommonFields({
  value,
  setField,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
}) {
  return (
    <Section title="Run">
      <div style={gridStyle}>
        <Field label="Output Name">
          <input
            value={stringValue(value.output_name)}
            onChange={(event) => setField("output_name", event.target.value || undefined)}
            placeholder="Defaults to task name"
            style={inputStyle}
          />
        </Field>
        <Field label="P Value Threshold">
          <input
            type="number"
            min="0"
            max="1"
            step="0.001"
            value={String(value.pvalue_threshold ?? 0.05)}
            onChange={(event) => setField("pvalue_threshold", Number(event.target.value || 0.05))}
            style={inputStyle}
          />
        </Field>
      </div>
    </Section>
  );
}

function DbAlignmentFields({
  value,
  setField,
  sourceContext,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
}) {
  const mapping = (value.field_mapping as Record<string, unknown> | undefined) || {};
  const pepColumns = sourceContext?.pepColumns || [];
  const groupFields = detectedGroupFields(sourceContext);
  return (
    <Section title="DB Alignment">
      <div style={gridStyle}>
        <ColumnSelect
          label="CDR3 Column"
          value={stringValue(mapping.cdr3_column)}
          options={pepColumns}
          onChange={(next) => setField("field_mapping", { ...mapping, cdr3_column: next })}
          emptyLabel="No PEP columns detected"
        />
        <ColumnSelect
          label="Copy Column"
          value={stringValue(mapping.copy_column)}
          options={pepColumns}
          onChange={(next) => setField("field_mapping", { ...mapping, copy_column: next })}
          emptyLabel="No PEP columns detected"
        />
        <ColumnMultiPicker
          label="Profile Categories"
          selected={stringList(value.categories)}
          options={groupFields}
          onChange={(next) => setField("categories", next)}
          emptyLabel="No Profile group fields detected"
        />
        <Field label="Pathology Values">
          <input
            value={listInput(value.pathology_values)}
            onChange={(event) => setField("pathology_values", splitList(event.target.value))}
            placeholder="optional value filter"
            style={inputStyle}
          />
        </Field>
        <SwitchField
          label="Contained Pathology"
          checked={Boolean(value.contained_pathology)}
          onChange={(checked) => setField("contained_pathology", checked)}
        />
      </div>
    </Section>
  );
}

function ProfileBoxplotFields({
  value,
  setField,
  sourceContext,
  groupSpecs,
  loadingSpecs,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
  groupSpecs: GroupSpec[];
  loadingSpecs: boolean;
}) {
  return (
    <Section title="Profile / Boxplot">
      <div style={gridStyle}>
        <RangeFields value={value} setField={setField} sourceContext={sourceContext} groupPrefix="classification" parameterLabels />
        <ColumnMultiPicker
          label="Group Type Fields"
          selected={stringList(value.grouptype_fields)}
          options={detectedGroupFields(sourceContext)}
          onChange={(next) => setField("grouptype_fields", next)}
          emptyLabel="No Profile group fields detected"
        />
        <Field label="Group Order">
          <input
            value={stringValue(value.group_order)}
            onChange={(event) => setField("group_order", event.target.value || undefined)}
            placeholder="Control,Treatment,Recovery"
            style={inputStyle}
          />
        </Field>
        <GroupSpecSelect value={value} setField={setField} groupSpecs={groupSpecs} loadingSpecs={loadingSpecs} />
      </div>
    </Section>
  );
}

function PepAnalysisFields({
  value,
  setField,
  sourceContext,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
}) {
  return (
    <Section title="PEP Shared Analysis">
      <div style={gridStyle}>
        <ColumnMultiPicker
          label="Group Fields"
          selected={stringList(value.group_fields)}
          options={detectedGroupFields(sourceContext)}
          onChange={(next) => setField("group_fields", next)}
          emptyLabel="No Profile group fields detected"
        />
        <Field label="Min Sample Threshold">
          <input
            type="number"
            min="1"
            value={String(value.min_sample_threshold ?? 3)}
            onChange={(event) => setField("min_sample_threshold", Number(event.target.value || 3))}
            style={inputStyle}
          />
        </Field>
        <ChainPicker value={value} setField={setField} sourceContext={sourceContext} />
        <ChipPicker
          label="Optional Steps"
          selected={stringList(value.optional_steps)}
          options={PEP_OPTIONAL_STEPS}
          onToggle={(next) => setField("optional_steps", next)}
        />
      </div>
    </Section>
  );
}

function PgenFields({
  value,
  setField,
  sourceContext,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
}) {
  return (
    <Section title="Pgen">
      <div style={gridStyle}>
        <ChainPicker value={value} setField={setField} sourceContext={sourceContext} disabled={["TRD", "TRG"]} />
        <Field label="Species">
          <select value={stringValue(value.species, "human")} onChange={(event) => setField("species", event.target.value)} style={inputStyle}>
            <option value="human">human</option>
            <option value="mouse">mouse</option>
          </select>
        </Field>
        <ColumnSelect label="Sample Column" value={stringValue(value.sample_col, "sample")} options={sourceContext?.profileFields || []} onChange={(next) => setField("sample_col", next || "sample")} emptyLabel="No Profile columns detected" />
        <ColumnSelect label="Distribution Category Column" value={stringValue(value.distribution_category_col)} options={detectedGroupFields(sourceContext)} onChange={(next) => setField("distribution_category_col", next || undefined)} emptyLabel="No Profile group fields detected" optional />
      </div>
    </Section>
  );
}

function TopCloneFields({
  value,
  setField,
  sourceContext,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
}) {
  return (
    <Section title="TopClone">
      <div style={gridStyle}>
        <Field label="Mode">
          <select value={stringValue(value.mode, "trace")} onChange={(event) => setField("mode", event.target.value)} style={inputStyle}>
            <option value="trace">trace</option>
            <option value="per_sample">per_sample</option>
          </select>
        </Field>
        <Field label="Top N">
          <input type="number" min="1" value={String(value.top_n ?? 10)} onChange={(event) => setField("top_n", Number(event.target.value || 10))} style={inputStyle} />
        </Field>
        <ColumnSelect label="Group Field" value={stringValue(value.group_field)} options={detectedGroupFields(sourceContext)} onChange={(next) => setField("group_field", next || undefined)} emptyLabel="No Profile group fields detected" optional />
        <Field label="Group Order">
          <input value={stringValue(value.group_order)} onChange={(event) => setField("group_order", event.target.value || undefined)} placeholder="optional comma order" style={inputStyle} />
        </Field>
        <ChainPicker value={value} setField={setField} sourceContext={sourceContext} />
      </div>
    </Section>
  );
}

function UmapFields({
  value,
  setField,
  sourceContext,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
}) {
  return (
    <Section title="UMAP">
      <div style={gridStyle}>
        <RangeFields value={value} setField={setField} sourceContext={sourceContext} groupPrefix="classification" parameterLabels />
        <Field label="n_neighbors">
          <input type="number" min="2" value={String(value.n_neighbors ?? 6)} onChange={(event) => setField("n_neighbors", Number(event.target.value || 6))} style={inputStyle} />
        </Field>
        <Field label="min_dist">
          <input type="number" min="0" max="1" step="0.01" value={String(value.min_dist ?? 0.01)} onChange={(event) => setField("min_dist", Number(event.target.value || 0.01))} style={inputStyle} />
        </Field>
      </div>
    </Section>
  );
}

function VolcanoFields({
  value,
  setField,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
}) {
  return (
    <Section title="Volcano">
      <div style={gridStyle}>
        <Field label="Input Mode">
          <select value={stringValue(value.input_mode, "expression")} onChange={(event) => setField("input_mode", event.target.value)} style={inputStyle}>
            <option value="expression">expression matrix</option>
            <option value="usage">VJ usage cache</option>
          </select>
        </Field>
        <ExpressionComparisonFields value={value} setField={setField} />
      </div>
    </Section>
  );
}

function GoKeggFields({
  value,
  setField,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
}) {
  return (
    <Section title="GO / KEGG">
      <div style={gridStyle}>
        <ExpressionComparisonFields value={value} setField={setField} />
        <Field label="Enrichment P Value">
          <input type="number" min="0" max="1" step="0.001" value={String(value.enrich_pvalue_cutoff ?? 0.05)} onChange={(event) => setField("enrich_pvalue_cutoff", Number(event.target.value || 0.05))} style={inputStyle} />
        </Field>
        <Field label="P Adjust Method">
          <select value={stringValue(value.p_adjust_method, "none")} onChange={(event) => setField("p_adjust_method", event.target.value)} style={inputStyle}>
            <option value="none">none</option>
            <option value="BH">BH</option>
            <option value="BY">BY</option>
            <option value="holm">holm</option>
            <option value="bonferroni">bonferroni</option>
          </select>
        </Field>
        <Field label="Show Category">
          <input type="number" min="1" value={String(value.show_category ?? 20)} onChange={(event) => setField("show_category", Number(event.target.value || 20))} style={inputStyle} />
        </Field>
        <SwitchField label="Simplify GO" checked={Boolean(value.simplify_go ?? true)} onChange={(checked) => setField("simplify_go", checked)} />
        <SwitchField label="Run GSEA" checked={Boolean(value.do_gsea ?? true)} onChange={(checked) => setField("do_gsea", checked)} />
      </div>
    </Section>
  );
}

function UmapinFields({
  value,
  setField,
  sourceContext,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
}) {
  return (
    <Section title="UMAPin">
      <div style={gridStyle}>
        <RangeFields value={value} setField={setField} sourceContext={sourceContext} />
        <ColumnSelect label="Category Column" value={stringValue(value.category_col, "Category")} options={detectedAnyColumns(sourceContext)} onChange={(next) => setField("category_col", next || "Category")} emptyLabel="No cached usage columns detected" />
        <Field label="n_neighbors">
          <input type="number" min="2" value={String(value.n_neighbors ?? 6)} onChange={(event) => setField("n_neighbors", Number(event.target.value || 6))} style={inputStyle} />
        </Field>
        <Field label="min_dist">
          <input type="number" min="0" max="1" step="0.01" value={String(value.min_dist ?? 0.01)} onChange={(event) => setField("min_dist", Number(event.target.value || 0.01))} style={inputStyle} />
        </Field>
        <SwitchField label="FDR Correction" checked={Boolean(value.do_fdr)} onChange={(checked) => setField("do_fdr", checked)} />
      </div>
    </Section>
  );
}

function MlFields({
  value,
  setField,
  sourceContext,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
}) {
  return (
    <Section title="Machine Learning">
      <div style={gridStyle}>
        <Field label="Feature Source">
          <select value={stringValue(value.mode, "profile")} onChange={(event) => setField("mode", event.target.value)} style={inputStyle}>
            <option value="profile">Profile feature range</option>
            <option value="vj-usage">VJ usage feature range</option>
          </select>
        </Field>
        <ColumnSelect label="Label Column" value={stringValue(value.label_col)} options={detectedGroupFields(sourceContext)} onChange={(next) => setField("label_col", next)} emptyLabel="No Profile group fields detected" />
        <ColumnSelect label="Sample Column" value={stringValue(value.sample_col, "Sample")} options={sourceContext?.profileFields || []} onChange={(next) => setField("sample_col", next || "Sample")} emptyLabel="No Profile columns detected" />
        <RangeFields value={value} setField={setField} sourceContext={sourceContext} />
        <Field label="Usage Path">
          <input value={stringValue(value.usage_path)} onChange={(event) => setField("usage_path", event.target.value || undefined)} placeholder="required for VJ usage mode" style={inputStyle} />
        </Field>
        <ColumnSelect label="Filter Column" value={stringValue(value.filter_col)} options={detectedGroupFields(sourceContext)} onChange={(next) => setField("filter_col", next || undefined)} emptyLabel="No Profile group fields detected" optional />
        <Field label="Filter Value">
          <input value={stringValue(value.filter_value)} onChange={(event) => setField("filter_value", event.target.value || undefined)} placeholder="optional" style={inputStyle} />
        </Field>
        <Field label="Custom Threshold">
          <input type="number" min="0" step="0.001" value={String(value.custom_threshold ?? 0.003)} onChange={(event) => setField("custom_threshold", Number(event.target.value || 0.003))} style={inputStyle} />
        </Field>
        <Field label="CV Splits">
          <input type="number" min="2" value={String(value.cv_splits ?? 3)} onChange={(event) => setField("cv_splits", Number(event.target.value || 3))} style={inputStyle} />
        </Field>
        <Field label="ROC CV Splits">
          <input type="number" min="2" value={String(value.roc_cv_splits ?? 7)} onChange={(event) => setField("roc_cv_splits", Number(event.target.value || 7))} style={inputStyle} />
        </Field>
      </div>
    </Section>
  );
}

function MaitNktFields({
  value,
  setField,
  sourceContext,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
}) {
  return (
    <Section title="MAIT / NKT">
      <div style={gridStyle}>
        <Field label="TRA Source">
          <select value={stringValue(value.tra_source, "upload")} onChange={(event) => setField("tra_source", event.target.value)} style={inputStyle}>
            <option value="upload">uploaded TRA CSV</option>
            <option value="pep_analysis">PEP shared result</option>
          </select>
        </Field>
        <Field label="TRA Path">
          <input value={stringValue(value.tra_path)} onChange={(event) => setField("tra_path", event.target.value || undefined)} placeholder="required for upload source" style={inputStyle} />
        </Field>
        <Field label="Source Job ID">
          <input value={stringValue(value.source_job_id)} onChange={(event) => setField("source_job_id", event.target.value || undefined)} placeholder="optional PEP result job id" style={inputStyle} />
        </Field>
        <ColumnSelect label="Group Field" value={stringValue(value.group_field)} options={detectedGroupFields(sourceContext)} onChange={(next) => setField("group_field", next)} emptyLabel="No Profile group fields detected" />
        <Field label="Group Order">
          <input value={stringValue(value.group_order)} onChange={(event) => setField("group_order", event.target.value || undefined)} placeholder="Control,Treatment,Recovery" style={inputStyle} />
        </Field>
      </div>
    </Section>
  );
}

function ChartsNotice() {
  return (
    <Section title="Charts">
      <div style={noticeStyle}>
        综合图表模块原版由页面内独立逻辑触发热图、Treemap、Chord。当前配置先保留入口，执行桥需要接入 `charts.combined` 或专用 ScriptHub charts endpoint。
      </div>
    </Section>
  );
}

function ExpressionComparisonFields({
  value,
  setField,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
}) {
  return (
    <>
      <Field label="Group Prefix">
        <input value={stringValue(value.group_prefix, "tpm_")} onChange={(event) => setField("group_prefix", event.target.value || "tpm_")} style={inputStyle} />
      </Field>
      <Field label="Comparisons">
        <input
          value={listInput(value.comparisons)}
          onChange={(event) => setField("comparisons", splitList(event.target.value))}
          placeholder="A_vs_B, C_vs_D"
          style={inputStyle}
        />
      </Field>
      <Field label="LogFC Cutoff">
        <input type="number" min="0" step="0.1" value={String(value.logfc_cutoff ?? 1)} onChange={(event) => setField("logfc_cutoff", Number(event.target.value || 1))} style={inputStyle} />
      </Field>
    </>
  );
}

function RangeFields({
  value,
  setField,
  sourceContext,
  groupPrefix,
  parameterLabels,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
  groupPrefix?: "classification";
  parameterLabels?: boolean;
}) {
  const profileFields = sourceContext?.profileFields || [];
  const groupFields = detectedGroupFields(sourceContext);
  return (
    <>
      {groupPrefix === "classification" && (
        <>
          <ColumnSelect label={parameterLabels ? "Group Begin Column" : "Classification Begin"} value={stringValue(value.classification_begin || value.grouping_begin)} options={groupFields} onChange={(next) => setField("classification_begin", next)} emptyLabel="No Profile group fields detected" />
          <ColumnSelect label={parameterLabels ? "Group End Column" : "Classification End"} value={stringValue(value.classification_over || value.grouping_over)} options={groupFields} onChange={(next) => setField("classification_over", next)} emptyLabel="No Profile group fields detected" />
        </>
      )}
      <ColumnSelect label="Parameter Begin" value={stringValue(value.param_begin)} options={profileFields} onChange={(next) => setField("param_begin", next)} emptyLabel="No Profile columns detected" />
      <ColumnSelect label="Parameter End" value={stringValue(value.param_over)} options={profileFields} onChange={(next) => setField("param_over", next)} emptyLabel="No Profile columns detected" />
    </>
  );
}

function GroupSpecSelect({
  value,
  setField,
  groupSpecs,
  loadingSpecs,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  groupSpecs: GroupSpec[];
  loadingSpecs: boolean;
}) {
  return (
    <Field label="Project Group Spec">
      <select
        value={stringValue(value.group_spec_id)}
        onChange={(event) => setField("group_spec_id", event.target.value || undefined)}
        disabled={loadingSpecs}
        style={inputStyle}
      >
        <option value="">Profile fields / none</option>
        {groupSpecs.map((spec) => (
          <option key={spec.id} value={spec.id}>{spec.name}</option>
        ))}
      </select>
    </Field>
  );
}

function ChainPicker({
  value,
  setField,
  sourceContext,
  disabled = [],
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
  disabled?: string[];
}) {
  const selected = stringList(value.selected_chains);
  const chains = sourceContext?.chains?.length ? sourceContext.chains : CHAIN_OPTIONS;
  return (
    <ChipPicker
      label="Chains"
      selected={selected}
      options={chains.map((chain) => ({ key: chain, label: disabled.includes(chain) ? `${chain} (skip)` : chain, disabled: disabled.includes(chain) }))}
      onToggle={(next) => setField("selected_chains", next)}
    />
  );
}

function ColumnSelect({
  label,
  value,
  options,
  onChange,
  emptyLabel,
  optional,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (next: string) => void;
  emptyLabel: string;
  optional?: boolean;
}) {
  const normalizedOptions = uniqueStrings(options);
  return (
    <Field label={label}>
      <select value={value} onChange={(event) => onChange(event.target.value)} disabled={!normalizedOptions.length} style={inputStyle}>
        <option value="">{normalizedOptions.length ? (optional ? "None" : "Select detected column") : emptyLabel}</option>
        {normalizedOptions.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    </Field>
  );
}

function ColumnMultiPicker({
  label,
  selected,
  options,
  onChange,
  emptyLabel,
}: {
  label: string;
  selected: string[];
  options: string[];
  onChange: (next: string[]) => void;
  emptyLabel: string;
}) {
  const normalizedOptions = uniqueStrings(options);
  if (!normalizedOptions.length) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        <span style={fieldLabelStyle}>{label}</span>
        <div style={{ ...noticeStyle, padding: "8px 10px" }}>{emptyLabel}</div>
      </div>
    );
  }
  return (
    <ChipPicker
      label={label}
      selected={selected}
      options={normalizedOptions.map((option) => ({ key: option, label: option }))}
      onToggle={onChange}
    />
  );
}

function ChipPicker({
  label,
  selected,
  options,
  onToggle,
}: {
  label: string;
  selected: string[];
  options: Array<{ key: string; label: string; disabled?: boolean }>;
  onToggle: (next: string[]) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <span style={fieldLabelStyle}>{label}</span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
        {options.map((option) => {
          const active = selected.includes(option.key);
          return (
            <button
              key={option.key}
              type="button"
              disabled={option.disabled}
              onClick={() => onToggle(active ? selected.filter((item) => item !== option.key) : [...selected, option.key])}
              style={{
                padding: "5px 10px",
                borderRadius: "var(--radius-pill)",
                border: "1px solid var(--separator)",
                background: active ? "var(--accent)" : "var(--bg-elevated)",
                color: active ? "#fff" : "var(--text-primary)",
                opacity: option.disabled ? 0.45 : 1,
                fontSize: "0.78rem",
                cursor: option.disabled ? "not-allowed" : "pointer",
              }}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SwitchField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", minHeight: "38px" }}>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      {label}
    </label>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset style={{ border: "1px solid var(--separator)", borderRadius: "var(--radius-control)", padding: "var(--spacing-md)", margin: 0 }}>
      <legend style={{ padding: "0 6px", fontSize: "0.72rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={labelStyle}>
      {label}
      {children}
    </label>
  );
}

function stringValue(value: unknown, fallback = "") {
  return value === undefined || value === null ? fallback : String(value);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item || "").trim()).filter(Boolean) : [];
}

function splitList(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function listInput(value: unknown) {
  return stringList(value).join(", ");
}

function uniqueStrings(value: string[]) {
  return Array.from(new Set(value.map((item) => String(item || "").trim()).filter(Boolean)));
}

function detectedGroupFields(sourceContext?: ScriptHubSourceContext) {
  const groupFields = sourceContext?.groupFields || [];
  if (groupFields.length) return uniqueStrings(groupFields);
  return uniqueStrings(
    (sourceContext?.profileFields || []).filter((field) => !["sample", "sample_id", "sample_name", "id"].includes(field.toLowerCase())),
  );
}

function detectedAnyColumns(sourceContext?: ScriptHubSourceContext) {
  return uniqueStrings([
    ...(sourceContext?.pepColumns || []),
    ...(sourceContext?.profileFields || []),
  ]);
}

function guessColumn(columns: string[], hints: string[]) {
  const normalized = uniqueStrings(columns);
  const exact = normalized.find((column) => hints.some((hint) => column.toLowerCase() === hint.toLowerCase()));
  if (exact) return exact;
  return normalized.find((column) => hints.some((hint) => column.toLowerCase().includes(hint.toLowerCase()))) || "";
}

const gridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "var(--spacing-md)",
};

const noticeStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
  padding: "var(--spacing-md)",
  borderRadius: "var(--radius-control)",
  border: "1px solid color-mix(in srgb, var(--accent) 24%, var(--separator))",
  background: "color-mix(in srgb, var(--accent) 7%, transparent)",
  color: "var(--text-secondary)",
  fontSize: "0.8rem",
};

const fieldLabelStyle: React.CSSProperties = {
  fontSize: "0.75rem",
  fontWeight: 600,
  textTransform: "uppercase",
  color: "var(--text-secondary)",
};

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
  fontSize: "0.75rem",
  fontWeight: 600,
  textTransform: "uppercase",
  color: "var(--text-secondary)",
};

const inputStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
  width: "100%",
  boxSizing: "border-box",
};
