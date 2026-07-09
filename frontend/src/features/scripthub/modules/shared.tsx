import { useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { GroupSpec } from "../../../shared/api/groupSpecs";
import { listPepCacheCandidates, readScriptHubGroupValues } from "../../../shared/api/scriptHub";
import type { PepCacheCandidate } from "../../../shared/api/scriptHub";
import type { ScriptHubSourceContext } from "../../jobs/forms";

export const CHAIN_OPTIONS = ["TRA", "TRB", "TRG", "TRD", "IGH", "IGK", "IGL"];

export function ModuleShell({
  title,
  detail,
  sourceContext,
  children,
}: {
  title: string;
  detail: string;
  sourceContext?: ScriptHubSourceContext;
  children: ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
      <div style={noticeStyle}>
        <strong style={{ color: "var(--text-primary)" }}>{title}</strong>
        <span>{detail}</span>
      </div>
      <SourceSummary sourceContext={sourceContext} />
      {children}
    </div>
  );
}

export function CommonRunFields({
  value,
  setField,
  sourceContext,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
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

function SamplePicker({
  value,
  setField,
  samples,
  disabledMessage,
  label = "Samples",
  selectedSamples,
  onSelectedSamplesChange,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  samples: string[];
  disabledMessage?: string;
  label?: string;
  selectedSamples?: string[];
  onSelectedSamplesChange?: (next: string[]) => void;
}) {
  const [keyword, setKeyword] = useState("");
  const sampleOptions = uniqueStrings(samples);
  const isControlled = Array.isArray(selectedSamples);
  const rawSelected = isControlled ? stringList(selectedSamples) : stringList(value.selected_samples);
  const hasExplicitSelection = isControlled || Array.isArray(value.selected_samples);
  const selected = rawSelected.filter((sample) => sampleOptions.includes(sample));
  const activeSelection = hasExplicitSelection ? selected : sampleOptions;
  const normalizedKeyword = keyword.trim().toLowerCase();
  const visibleSamples = sampleOptions.filter((sample) => {
    const lower = sample.toLowerCase();
    return !normalizedKeyword || lower.includes(normalizedKeyword);
  });

  useEffect(() => {
    if (isControlled) return;
    const rawSelected = stringList(value.selected_samples);
    if (!sampleOptions.length) {
      if (rawSelected.length) setField("selected_samples", []);
      return;
    }
    if (!hasExplicitSelection) {
      setField("selected_samples", sampleOptions);
      return;
    }
    if (selected.length !== rawSelected.length) {
      setField("selected_samples", selected);
    }
  }, [sampleOptions.join("\n")]);

  if (!sampleOptions.length) {
    return <div style={{ ...groupPreviewStyle, color: "var(--text-tertiary)" }}>{disabledMessage || "Select group values to load valid samples."}</div>;
  }

  const setSelected = (next: string[]) => {
    const clean = uniqueStrings(next).filter((sample) => sampleOptions.includes(sample));
    if (isControlled && onSelectedSamplesChange) {
      onSelectedSamplesChange(clean);
      return;
    }
    setField("selected_samples", clean);
  };
  const selectVisible = () => setSelected(uniqueStrings([...activeSelection, ...visibleSamples]));
  const onlyVisible = () => setSelected(visibleSamples);
  const invertVisible = () => setSelected(uniqueStrings([
    ...activeSelection.filter((sample) => !visibleSamples.includes(sample)),
    ...visibleSamples.filter((sample) => !activeSelection.includes(sample)),
  ]));
  return (
    <div style={{ marginTop: "var(--spacing-md)", display: "grid", gap: "8px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(160px, 1fr)", gap: "var(--spacing-xs)" }}>
        <input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="Filter samples by keyword"
          style={inputStyle}
        />
      </div>
      <ChipPicker
        label={`${label} (${activeSelection.length}/${sampleOptions.length}, ${visibleSamples.length} visible)`}
        selected={activeSelection}
        options={visibleSamples.map((sample) => ({ key: sample, label: sample }))}
        onToggle={setSelected}
      />
      <div style={{ display: "flex", gap: "var(--spacing-xs)", marginTop: "6px", flexWrap: "wrap" }}>
        <button type="button" onClick={() => setSelected(sampleOptions)} style={miniButtonStyle}>All samples</button>
        <button type="button" onClick={selectVisible} disabled={!visibleSamples.length} style={miniButtonStyle}>Select visible</button>
        <button type="button" onClick={onlyVisible} disabled={!visibleSamples.length} style={miniButtonStyle}>Only visible</button>
        <button type="button" onClick={invertVisible} disabled={!visibleSamples.length} style={miniButtonStyle}>Invert visible</button>
        <button type="button" onClick={() => setSelected([])} style={miniButtonStyle}>Clear</button>
        <button type="button" onClick={() => setSelected(sampleOptions.slice(0, 5))} style={miniButtonStyle}>First 5</button>
        <button type="button" onClick={() => setSelected(sampleOptions.slice(0, 20))} style={miniButtonStyle}>First 20</button>
      </div>
    </div>
  );
}

export function SourceSummary({ sourceContext }: { sourceContext?: ScriptHubSourceContext }) {
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

export function PepCacheCardSelector({
  sourceContext,
  cacheType,
  value,
  onSelect,
  label = "PEP Cache",
  emptyText = "No PEP cache candidates found. Run Pep Analysis first.",
}: {
  sourceContext?: ScriptHubSourceContext;
  cacheType: "volcano" | "umapin" | "mait-nkt" | "usage" | "vj_usage" | "tra_shared" | string;
  value?: string;
  onSelect: (candidate: PepCacheCandidate) => void;
  label?: string;
  emptyText?: string;
}) {
  const [candidates, setCandidates] = useState<PepCacheCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState("");
  const projectId = sourceContext?.projectId || "";

  useEffect(() => {
    if (!projectId) {
      setCandidates([]);
      setNote("Select a project asset set to load PEP caches.");
      return;
    }
    let cancelled = false;
    setLoading(true);
    setNote("");
    listPepCacheCandidates(projectId, cacheType)
      .then((response) => {
        if (cancelled) return;
        setCandidates(response.candidates || []);
      })
      .catch((error) => {
        if (!cancelled) setNote(error instanceof Error ? error.message : "Failed to load PEP caches");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, cacheType]);

  const selectedValue = stringValue(value);
  const availableCandidates = useMemo(
    () => candidates.filter((candidate) => candidate.status !== "missing"),
    [candidates],
  );
  const selectedCandidate = useMemo(
    () => findSelectedPepCache(candidates, selectedValue),
    [candidates, selectedValue],
  );
  const selectValue = selectedCandidate?.id || "";
  return (
    <div style={pepCacheSelectorStyle}>
      <div style={pepCacheHeaderStyle}>
        <span style={fieldLabelStyle}>{label}</span>
        {!!candidates.length && (
          <span style={pepCacheCountStyle}>
            {availableCandidates.length}/{candidates.length} ready
          </span>
        )}
      </div>
      {loading && <div style={cacheEmptyStyle}>Loading PEP caches...</div>}
      {!loading && note && <div style={cacheEmptyStyle}>{note}</div>}
      {!loading && !note && !candidates.length && <div style={cacheEmptyStyle}>{emptyText}</div>}
      {!!candidates.length && (
        <>
          <select
            value={selectValue}
            onChange={(event) => {
              const next = candidates.find((candidate) => candidate.id === event.target.value);
              if (next && next.status !== "missing") onSelect(next);
            }}
            style={pepCacheSelectStyle}
          >
            <option value="">Select PEP cache</option>
            {candidates.map((candidate) => {
              const available = candidate.status !== "missing";
              return (
                <option key={candidate.id} value={candidate.id} disabled={!available}>
                  {pepCacheOptionLabel(candidate)}
                </option>
              );
            })}
          </select>
          {selectedCandidate ? (
            <PepCacheSummary candidate={selectedCandidate} />
          ) : (
            <div style={cacheEmptyStyle}>
              Select one ready PEP cache. Full cache paths are hidden; the selected cache id is submitted automatically.
            </div>
          )}
        </>
      )}
    </div>
  );
}

function findSelectedPepCache(candidates: PepCacheCandidate[], selectedValue: string) {
  if (!selectedValue) return undefined;
  return candidates.find((candidate) => (
    candidate.path === selectedValue
    || candidate.id === selectedValue
    || candidate.asset_id === selectedValue
    || candidate.job_id === selectedValue
  ));
}

function pepCacheOptionLabel(candidate: PepCacheCandidate) {
  const name = candidate.label || candidate.usage_type || candidate.cache_type || "PEP cache";
  const bits = [
    candidate.usage_type || candidate.cache_type,
    candidate.chains?.length ? candidate.chains.join("/") : "",
    candidate.group_field || (candidate.group_fields || []).join(", "),
    candidate.file_count !== undefined ? `${candidate.file_count} files` : "",
    candidate.status === "missing" ? "missing" : "",
  ].filter(Boolean);
  return bits.length ? `${name} · ${bits.join(" · ")}` : name;
}

function PepCacheSummary({ candidate }: { candidate: PepCacheCandidate }) {
  const ready = candidate.status !== "missing";
  const source = candidate.source_module || candidate.source || "pep-analysis";
  const jobText = candidate.job_id ? `Job ${shortId(candidate.job_id)}` : "Project cache";
  const groupText = candidate.group_field || (candidate.group_fields || []).join(", ");
  return (
    <div
      style={{
        ...pepCacheSummaryStyle,
        borderColor: ready ? "color-mix(in srgb, var(--accent) 42%, var(--separator))" : "var(--warning)",
        background: ready ? "color-mix(in srgb, var(--accent) 7%, var(--bg-elevated))" : "var(--bg-inset)",
      }}
    >
      <div style={pepCacheSummaryTopStyle}>
        <div style={{ minWidth: 0 }}>
          <strong style={pepCacheTitleStyle}>{candidate.label || candidate.usage_type || "PEP cache"}</strong>
          <div style={cacheMetaStyle}>{source} · {jobText}</div>
        </div>
        <span style={{ ...cacheBadgeStyle, color: ready ? "var(--success)" : "var(--warning)" }}>
          {ready ? "Ready" : "Missing"}
        </span>
      </div>
      <div style={pepCacheChipRowStyle}>
        <span style={pepCacheChipStyle}>{candidate.usage_type || candidate.cache_type || "cache"}</span>
        {!!candidate.chains?.length && <span style={pepCacheChipStyle}>{candidate.chains.join(" / ")}</span>}
        {!!groupText && <span style={pepCacheChipStyle}>Group: {groupText}</span>}
        {candidate.sample_count !== undefined && <span style={pepCacheChipStyle}>{candidate.sample_count} samples</span>}
        {!!candidate.data_types?.length && <span style={pepCacheChipStyle}>{candidate.data_types.join(" + ")}</span>}
        {!!candidate.available_for?.length && <span style={pepCacheChipStyle}>For: {candidate.available_for.join(", ")}</span>}
        {candidate.file_count !== undefined && <span style={pepCacheChipStyle}>{candidate.file_count} files</span>}
        {!!candidate.created_at && <span style={pepCacheChipStyle}>{formatCacheDate(candidate.created_at)}</span>}
      </div>
    </div>
  );
}

function shortId(value: string) {
  const text = String(value || "").trim();
  return text.length > 12 ? `${text.slice(0, 8)}...` : text;
}

function formatCacheDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString();
}

export function RangeFields({
  value,
  setField,
  sourceContext,
  groupPrefix,
  parameterLabels,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
  groupPrefix?: "classification" | "grouping";
  parameterLabels?: boolean;
}) {
  const profileFields = sourceContext?.profileFields || [];
  const groupFields = detectedGroupFields(sourceContext);
  const beginKey = groupPrefix === "grouping" ? "grouping_begin" : "classification_begin";
  const overKey = groupPrefix === "grouping" ? "grouping_over" : "classification_over";
  return (
    <>
      {groupPrefix && (
        <>
          <ColumnSelect label={parameterLabels ? "Group Begin Column" : "Classification Begin"} value={stringValue(value[beginKey])} options={groupFields} onChange={(next) => setField(beginKey, next)} emptyLabel="No Profile group fields detected" />
          <ColumnSelect label={parameterLabels ? "Group End Column" : "Classification End"} value={stringValue(value[overKey])} options={groupFields} onChange={(next) => setField(overKey, next)} emptyLabel="No Profile group fields detected" />
        </>
      )}
      <ColumnSelect label="Parameter Begin" value={stringValue(value.param_begin)} options={profileFields} onChange={(next) => setField("param_begin", next)} emptyLabel="No Profile columns detected" />
      <ColumnSelect label="Parameter End" value={stringValue(value.param_over)} options={profileFields} onChange={(next) => setField("param_over", next)} emptyLabel="No Profile columns detected" />
    </>
  );
}

export function GroupSpecSelect({
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

export function ChainPicker({
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

export function ColumnSelect({
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

export function GroupFieldSelect({
  label = "Group Field",
  value,
  sourceContext,
  onChange,
  emptyLabel = "No Profile group fields detected",
  optional,
}: {
  label?: string;
  value: string;
  sourceContext?: ScriptHubSourceContext;
  onChange: (next: string) => void;
  emptyLabel?: string;
  optional?: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <ColumnSelect
        label={label}
        value={value}
        options={detectedGroupFields(sourceContext)}
        onChange={onChange}
        emptyLabel={emptyLabel}
        optional={optional}
      />
      <GroupValuesPreview sourceContext={sourceContext} fields={value ? [value] : []} />
    </div>
  );
}

export function GroupFieldMultiSelect({
  label,
  selected,
  sourceContext,
  onChange,
  emptyLabel = "No Profile group fields detected",
  reorderable = true,
}: {
  label: string;
  selected: string[];
  sourceContext?: ScriptHubSourceContext;
  onChange: (next: string[]) => void;
  emptyLabel?: string;
  reorderable?: boolean;
}) {
  const options = detectedGroupFields(sourceContext);
  const normalizedSelected = uniqueStrings(selected);
  const availableOptions = options.filter((option) => !normalizedSelected.includes(option));
  const [candidate, setCandidate] = useState("");
  const [draggedField, setDraggedField] = useState<string | null>(null);

  useEffect(() => {
    if (candidate && !availableOptions.includes(candidate)) {
      setCandidate("");
    }
  }, [candidate, availableOptions.join("\n")]);

  if (!options.length) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        <span style={fieldLabelStyle}>{label}</span>
        <div style={{ ...noticeStyle, padding: "8px 10px" }}>{emptyLabel}</div>
      </div>
    );
  }

  const addCandidate = () => {
    if (!candidate) return;
    onChange(uniqueStrings([...normalizedSelected, candidate]));
    setCandidate("");
  };
  const dropSelected = (target: string) => {
    if (!draggedField || draggedField === target) return;
    onChange(reorderList(normalizedSelected, draggedField, target));
    setDraggedField(null);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      <span style={fieldLabelStyle}>{label}</span>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "var(--spacing-xs)" }}>
        <select value={candidate} onChange={(event) => setCandidate(event.target.value)} style={inputStyle}>
          <option value="">{availableOptions.length ? "Select group field" : "All detected group fields selected"}</option>
          {availableOptions.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={addCandidate}
          disabled={!candidate}
          style={{
            minHeight: "38px",
            padding: "0 12px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: candidate ? "var(--accent)" : "var(--bg-inset)",
            color: candidate ? "#fff" : "var(--text-tertiary)",
            cursor: candidate ? "pointer" : "not-allowed",
            fontSize: "0.78rem",
            fontWeight: 600,
          }}
        >
          Add
        </button>
      </div>
      {normalizedSelected.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
          {normalizedSelected.map((field, index) => (
            <div
              key={field}
              draggable={reorderable}
              data-testid={`group-field-chip-${field}`}
              onDragStart={() => reorderable && setDraggedField(field)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => reorderable && dropSelected(field)}
              onDragEnd={() => setDraggedField(null)}
              style={{ ...orderedChipStyle, opacity: draggedField === field ? 0.55 : 1 }}
            >
              {reorderable && <span title="Drag to reorder" style={dragHandleStyle}>::</span>}
              <span>{index + 1}. {field}</span>
              <button type="button" onClick={() => onChange(normalizedSelected.filter((item) => item !== field))} title="Remove field" style={miniButtonStyle}>Remove</button>
            </div>
          ))}
        </div>
      )}
      <GroupValuesPreview sourceContext={sourceContext} fields={normalizedSelected} />
    </div>
  );
}

export function GroupOrderEditor({
  selectedFields,
  sourceContext,
  value,
  onChange,
}: {
  selectedFields: string[];
  sourceContext?: ScriptHubSourceContext;
  value: unknown;
  onChange: (next: string | undefined) => void;
}) {
  const profilePath = sourceContext?.profilePath || "";
  const fields = uniqueStrings(selectedFields);
  const [state, setState] = useState<Record<string, { values: string[]; loading?: boolean; error?: string }>>({});
  const [draggedGroup, setDraggedGroup] = useState<{ field: string; group: string } | null>(null);

  useEffect(() => {
    if (!profilePath || !fields.length) {
      setState({});
      return;
    }
    let cancelled = false;
    setState((current) => {
      const next: Record<string, { values: string[]; loading?: boolean; error?: string }> = {};
      for (const field of fields) {
        next[field] = current[field] || { values: [], loading: true };
      }
      return next;
    });
    for (const field of fields) {
      readScriptHubGroupValues(profilePath, field)
        .then((data) => {
          if (cancelled) return;
          setState((current) => ({
            ...current,
            [field]: { values: Array.isArray(data.values) ? data.values.map(String) : [] },
          }));
        })
        .catch((error) => {
          if (cancelled) return;
          setState((current) => ({
            ...current,
            [field]: { values: [], error: error instanceof Error ? error.message : "Failed to load group values" },
          }));
        });
    }
    return () => {
      cancelled = true;
    };
  }, [profilePath, fields.join("\n")]);

  if (!fields.length) return null;

  const orderMap = parseGroupOrder(value, fields);
  const writeOrder = (field: string, order: string[]) => {
    const next: Record<string, string> = {};
    for (const item of fields) {
      const values = state[item]?.values || [];
      const resolved = item === field ? order : resolveGroupOrder(orderMap[item], values);
      if (resolved.length) next[item] = resolved.join(",");
    }
    onChange(Object.keys(next).length ? JSON.stringify(next) : undefined);
  };
  const dropGroup = (field: string, group: string) => {
    if (!draggedGroup || draggedGroup.field !== field || draggedGroup.group === group) return;
    const values = state[field]?.values || [];
    const order = resolveGroupOrder(orderMap[field], values);
    writeOrder(field, reorderList(order, draggedGroup.group, group));
    setDraggedGroup(null);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px", gridColumn: "1 / -1" }}>
      <span style={fieldLabelStyle}>Group Order</span>
      {fields.map((field) => {
        const item = state[field];
        const values = item?.values || [];
        const order = resolveGroupOrder(orderMap[field], values);
        return (
          <div key={field} style={groupPreviewStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px", flexWrap: "wrap" }}>
              <strong style={{ color: "var(--text-primary)", fontSize: "0.78rem" }}>{field}</strong>
              {item?.loading && <span>loading groups...</span>}
              {item?.error && <span style={{ color: "var(--danger)" }}>{item.error}</span>}
              {!item?.loading && !item?.error && values.length > 0 && (
                <button type="button" onClick={() => writeOrder(field, values)} style={miniButtonStyle}>Reset detected order</button>
              )}
            </div>
            {!item?.loading && !item?.error && order.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
                {order.map((group, index) => (
                  <div
                    key={group}
                    draggable
                    data-testid={`group-order-row-${field}-${group}`}
                    onDragStart={() => setDraggedGroup({ field, group })}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={() => dropGroup(field, group)}
                    onDragEnd={() => setDraggedGroup(null)}
                    style={{ ...orderedChipStyle, padding: "4px 7px", opacity: draggedGroup?.field === field && draggedGroup.group === group ? 0.55 : 1 }}
                  >
                    <span title="Drag to reorder" style={dragHandleStyle}>::</span>
                    <span>{index + 1}. {group}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function GroupValueSamplePicker({
  value,
  setField,
  sourceContext,
  fields,
}: {
  value: Record<string, unknown>;
  setField: (key: string, next: unknown) => void;
  sourceContext?: ScriptHubSourceContext;
  fields: string[];
}) {
  const profilePath = sourceContext?.profilePath || "";
  const selectedFields = uniqueStrings(fields);
  const selectedGroupValues = recordStringLists(value.selected_group_values);
  const selectedSamplesByGroup = recordNestedSampleSelections(value.selected_samples_by_group);
  const [state, setState] = useState<Record<string, { values: string[]; samplesByValue: Record<string, string[]>; loading?: boolean; error?: string }>>({});

  useEffect(() => {
    if (!profilePath || !selectedFields.length) {
      setState({});
      return;
    }
    let cancelled = false;
    setState((current) => {
      const next: Record<string, { values: string[]; samplesByValue: Record<string, string[]>; loading?: boolean; error?: string }> = {};
      for (const field of selectedFields) {
        next[field] = current[field] || { values: [], samplesByValue: {}, loading: true };
      }
      return next;
    });
    for (const field of selectedFields) {
      readScriptHubGroupValues(profilePath, field)
        .then((data) => {
          if (cancelled) return;
          setState((current) => ({
            ...current,
            [field]: {
              values: Array.isArray(data.values) ? data.values.map(String) : [],
              samplesByValue: data.samples_by_value || {},
            },
          }));
        })
        .catch((error) => {
          if (cancelled) return;
          setState((current) => ({
            ...current,
            [field]: {
              values: [],
              samplesByValue: {},
              error: error instanceof Error ? error.message : "Failed to load group values",
            },
          }));
        });
    }
    return () => {
      cancelled = true;
    };
  }, [profilePath, selectedFields.join("\n")]);

  const writeGroupValues = (field: string, nextValues: string[]) => {
    const next = { ...selectedGroupValues, [field]: uniqueStrings(nextValues) };
    for (const key of Object.keys(next)) {
      if (!selectedFields.includes(key) || !next[key].length) delete next[key];
    }
    setField("selected_group_values", Object.keys(next).length ? next : undefined);
  };

  const hasSelectedValues = selectedFields.some((field) => (selectedGroupValues[field] || []).length);
  const sampleStateSignature = selectedFields.map((field) => {
    const samplesByValue = state[field]?.samplesByValue || {};
    return (selectedGroupValues[field] || []).map((groupValue) => `${field}:${groupValue}:${(samplesByValue[groupValue] || []).join("\t")}`).join("|");
  }).join("\n");

  const buildSamplesByGroup = (raw: Record<string, Record<string, string[]>>) => {
    const next: Record<string, Record<string, string[]>> = {};
    for (const field of selectedFields) {
      const selectedValues = selectedGroupValues[field] || [];
      const samplesByValue = state[field]?.samplesByValue || {};
      for (const groupValue of selectedValues) {
        const options = uniqueStrings(samplesByValue[groupValue] || []);
        const rawField = raw[field] || {};
        const hasExplicitGroupSelection = Object.prototype.hasOwnProperty.call(rawField, groupValue);
        const clean = hasExplicitGroupSelection
          ? uniqueStrings(rawField[groupValue] || []).filter((sample) => options.includes(sample))
          : options;
        if (!next[field]) next[field] = {};
        next[field][groupValue] = clean;
      }
    }
    return next;
  };

  const writeSamplesByGroup = (nextRaw: Record<string, Record<string, string[]>>) => {
    const next = buildSamplesByGroup(nextRaw);
    setField("selected_samples_by_group", Object.keys(next).length ? next : undefined);
  };

  useEffect(() => {
    if (!hasSelectedValues) {
      if (Object.keys(selectedSamplesByGroup).length) setField("selected_samples_by_group", undefined);
      return;
    }
    const next = buildSamplesByGroup(selectedSamplesByGroup);
    if (JSON.stringify(next) !== JSON.stringify(selectedSamplesByGroup)) {
      setField("selected_samples_by_group", next);
    }
  }, [selectedFields.join("\n"), JSON.stringify(selectedGroupValues), sampleStateSignature]);

  if (!selectedFields.length) {
    return <div style={{ ...groupPreviewStyle, gridColumn: "1 / -1", color: "var(--text-tertiary)" }}>Please select group field before choosing samples.</div>;
  }
  if (!profilePath) {
    return <div style={{ ...groupPreviewStyle, gridColumn: "1 / -1", color: "var(--text-tertiary)" }}>Select a Profile file to load group values and valid samples.</div>;
  }

  return (
    <div style={{ display: "grid", gap: "10px", gridColumn: "1 / -1" }}>
      <span style={fieldLabelStyle}>Group Values</span>
      {selectedFields.map((field) => {
        const item = state[field];
        const values = item?.values || [];
        const selected = selectedGroupValues[field] || [];
        return (
          <div key={field} style={groupPreviewStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px", flexWrap: "wrap" }}>
              <strong style={{ color: "var(--text-primary)", fontSize: "0.78rem" }}>{field}</strong>
              {item?.loading && <span>loading groups...</span>}
              {item?.error && <span style={{ color: "var(--danger)" }}>{item.error}</span>}
              {!item?.loading && !item?.error && values.length > 0 && (
                <>
                  <button type="button" onClick={() => writeGroupValues(field, values)} style={miniButtonStyle}>All groups</button>
                  <button type="button" onClick={() => writeGroupValues(field, [])} style={miniButtonStyle}>Clear groups</button>
                </>
              )}
            </div>
            {!item?.loading && !item?.error && values.length > 0 && (
              <ChipPicker
                label={`${selected.length}/${values.length} selected`}
                selected={selected}
                options={values.map((groupValue) => ({
                  key: groupValue,
                  label: `${groupValue} (${(item?.samplesByValue[groupValue] || []).length})`,
                }))}
                onToggle={(next) => writeGroupValues(field, next)}
              />
            )}
            {!item?.loading && !item?.error && selected.length > 0 && (
              <div style={{ display: "grid", gap: "8px", marginTop: "8px" }}>
                {selected.map((groupValue) => {
                  const groupSamples = uniqueStrings(item?.samplesByValue[groupValue] || []);
                  const fieldSelections = selectedSamplesByGroup[field] || {};
                  const selectedSamples = Object.prototype.hasOwnProperty.call(fieldSelections, groupValue)
                    ? fieldSelections[groupValue]
                    : groupSamples;
                  return (
                    <div key={groupValue} style={{ ...groupPreviewStyle, background: "var(--bg-elevated)" }}>
                      <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "var(--text-secondary)", marginBottom: "4px" }}>
                        {field} = {groupValue}
                      </div>
                      <SamplePicker
                        value={value}
                        setField={setField}
                        samples={groupSamples}
                        label={`${groupValue} samples`}
                        selectedSamples={selectedSamples}
                        onSelectedSamplesChange={(nextSamples) => {
                          writeSamplesByGroup({
                            ...selectedSamplesByGroup,
                            [field]: {
                              ...(selectedSamplesByGroup[field] || {}),
                              [groupValue]: nextSamples,
                            },
                          });
                        }}
                        disabledMessage="No samples found for this group value."
                      />
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
      {!hasSelectedValues && (
        <div style={{ ...groupPreviewStyle, color: "var(--text-tertiary)" }}>
          Select group values first; then choose samples inside each group.
        </div>
      )}
    </div>
  );
}

function GroupValuesPreview({
  sourceContext,
  fields,
}: {
  sourceContext?: ScriptHubSourceContext;
  fields: string[];
}) {
  const profilePath = sourceContext?.profilePath || "";
  const normalizedFields = uniqueStrings(fields);
  const [state, setState] = useState<Record<string, { values: string[]; loading?: boolean; error?: string }>>({});

  useEffect(() => {
    if (!profilePath || !normalizedFields.length) {
      setState({});
      return;
    }
    let cancelled = false;
    setState((current) => {
      const next: Record<string, { values: string[]; loading?: boolean; error?: string }> = {};
      for (const field of normalizedFields) {
        next[field] = current[field] || { values: [], loading: true };
      }
      return next;
    });
    for (const field of normalizedFields) {
      readScriptHubGroupValues(profilePath, field)
        .then((data) => {
          if (cancelled) return;
          setState((current) => ({
            ...current,
            [field]: { values: Array.isArray(data.values) ? data.values.map(String) : [] },
          }));
        })
        .catch((error) => {
          if (cancelled) return;
          setState((current) => ({
            ...current,
            [field]: { values: [], error: error instanceof Error ? error.message : "Failed to load group values" },
          }));
        });
    }
    return () => {
      cancelled = true;
    };
  }, [profilePath, normalizedFields.join("\n")]);

  if (!normalizedFields.length) return null;
  if (!profilePath) {
    return <div style={{ ...groupPreviewStyle, color: "var(--text-tertiary)" }}>Select a Profile file to preview group values.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {normalizedFields.map((field) => {
        const item = state[field];
        const values = item?.values || [];
        return (
          <div key={field} style={groupPreviewStyle}>
            <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-secondary)" }}>
              {field}: {item?.loading ? "loading groups..." : item?.error ? item.error : `${values.length} groups`}
            </div>
            {!item?.loading && !item?.error && values.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginTop: "5px" }}>
                {values.slice(0, 24).map((value) => (
                  <span key={value} style={groupValueChipStyle}>{value}</span>
                ))}
                {values.length > 24 && <span style={groupValueChipStyle}>+{values.length - 24} more</span>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function ColumnMultiPicker({
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

export function ChipPicker({
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

export function SwitchField({
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

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset style={{ border: "1px solid var(--separator)", borderRadius: "var(--radius-control)", padding: "var(--spacing-md)", margin: 0 }}>
      <legend style={{ padding: "0 6px", fontSize: "0.72rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={labelStyle}>
      {label}
      {children}
    </label>
  );
}

export function setFieldValue(
  value: Record<string, unknown>,
  onChange: (v: Record<string, unknown>) => void,
  key: string,
  next: unknown,
) {
  onChange({ ...value, [key]: next });
}

export function withDefaults(value: Record<string, unknown>, defaults: Record<string, unknown>) {
  return { ...defaults, ...value };
}

export function useSyncedDefaults(
  value: Record<string, unknown>,
  current: Record<string, unknown>,
  onChange: (v: Record<string, unknown>) => void,
) {
  const currentSignature = JSON.stringify(current);
  const valueSignature = JSON.stringify(value);
  useEffect(() => {
    if (currentSignature !== valueSignature) {
      onChange(current);
    }
  }, [currentSignature, valueSignature, current, onChange]);
}

export function stringValue(value: unknown, fallback = "") {
  return value === undefined || value === null ? fallback : String(value);
}

export function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item || "").trim()).filter(Boolean) : [];
}

function recordStringLists(value: unknown): Record<string, string[]> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result: Record<string, string[]> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    const list = stringList(item);
    if (list.length) result[key] = list;
  }
  return result;
}

function recordNestedSampleSelections(value: unknown): Record<string, Record<string, string[]>> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result: Record<string, Record<string, string[]>> = {};
  for (const [field, groups] of Object.entries(value as Record<string, unknown>)) {
    if (!groups || typeof groups !== "object" || Array.isArray(groups)) continue;
    const nested: Record<string, string[]> = {};
    for (const [groupValue, samples] of Object.entries(groups as Record<string, unknown>)) {
      if (Array.isArray(samples)) nested[groupValue] = uniqueStrings(samples.map(String));
    }
    if (Object.keys(nested).length) result[field] = nested;
  }
  return result;
}

export function splitList(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function listInput(value: unknown) {
  return stringList(value).join(", ");
}

export function uniqueStrings(value: string[]) {
  return Array.from(new Set(value.map((item) => String(item || "").trim()).filter(Boolean)));
}

function reorderList(values: string[], dragged: string, target: string) {
  const next = [...values];
  const from = next.indexOf(dragged);
  const to = next.indexOf(target);
  if (from < 0 || to < 0 || from === to) return next;
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

function parseGroupOrder(value: unknown, fields: string[]) {
  const text = stringValue(value).trim();
  const result: Record<string, string[]> = {};
  if (!text) return result;
  try {
    const parsed = JSON.parse(text) as Record<string, unknown>;
    for (const field of fields) {
      const item = parsed[field];
      if (Array.isArray(item)) {
        result[field] = uniqueStrings(item.map(String));
      } else if (typeof item === "string") {
        result[field] = splitList(item);
      }
    }
    return result;
  } catch {
    const shared = splitList(text);
    for (const field of fields) result[field] = shared;
    return result;
  }
}

function resolveGroupOrder(order: string[] | undefined, values: string[]) {
  const normalizedValues = uniqueStrings(values);
  const normalizedOrder = uniqueStrings(order || []);
  return [
    ...normalizedOrder.filter((item) => normalizedValues.includes(item)),
    ...normalizedValues.filter((item) => !normalizedOrder.includes(item)),
  ];
}

export function detectedGroupFields(sourceContext?: ScriptHubSourceContext) {
  const groupFields = sourceContext?.groupFields || [];
  if (groupFields.length) return uniqueStrings(groupFields);
  return uniqueStrings(
    (sourceContext?.profileFields || []).filter((field) => !["sample", "sample_id", "sample_name", "id"].includes(field.toLowerCase())),
  );
}

export function guessColumn(columns: string[], hints: string[]) {
  const normalized = uniqueStrings(columns);
  const exact = normalized.find((column) => hints.some((hint) => column.toLowerCase() === hint.toLowerCase()));
  if (exact) return exact;
  return normalized.find((column) => hints.some((hint) => column.toLowerCase().includes(hint.toLowerCase()))) || "";
}

export const gridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "var(--spacing-md)",
};

export const noticeStyle: CSSProperties = {
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

export const fieldLabelStyle: CSSProperties = {
  fontSize: "0.75rem",
  fontWeight: 600,
  textTransform: "uppercase",
  color: "var(--text-secondary)",
};

const groupPreviewStyle: CSSProperties = {
  padding: "8px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-inset)",
  textTransform: "none",
};

const groupValueChipStyle: CSSProperties = {
  padding: "3px 7px",
  borderRadius: "var(--radius-pill)",
  background: "var(--bg-elevated)",
  border: "1px solid var(--separator)",
  color: "var(--text-primary)",
  fontSize: "0.72rem",
};

const cacheEmptyStyle: CSSProperties = {
  padding: "8px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-inset)",
  color: "var(--text-secondary)",
  fontSize: "0.78rem",
  textTransform: "none",
};

const pepCacheSelectorStyle: CSSProperties = {
  display: "grid",
  gap: "8px",
  gridColumn: "1 / -1",
};

const pepCacheHeaderStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "10px",
  minWidth: 0,
};

const pepCacheCountStyle: CSSProperties = {
  color: "var(--text-tertiary)",
  fontSize: "0.72rem",
  fontWeight: 600,
  whiteSpace: "nowrap",
};

const pepCacheSelectStyle: CSSProperties = {
  width: "100%",
  minHeight: "38px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  padding: "0 10px",
  fontSize: "0.82rem",
};

const pepCacheSummaryStyle: CSSProperties = {
  minWidth: 0,
  padding: "10px 12px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  color: "var(--text-primary)",
  display: "grid",
  gap: "8px",
};

const pepCacheSummaryTopStyle: CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: "10px",
  minWidth: 0,
};

const pepCacheTitleStyle: CSSProperties = {
  display: "block",
  maxWidth: "100%",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  fontSize: "0.86rem",
};

const pepCacheChipRowStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "6px",
  minWidth: 0,
};

const pepCacheChipStyle: CSSProperties = {
  maxWidth: "100%",
  padding: "3px 7px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-root)",
  color: "var(--text-secondary)",
  fontSize: "0.72rem",
  lineHeight: 1.25,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const cacheBadgeStyle: CSSProperties = {
  fontSize: "0.66rem",
  fontWeight: 700,
  textTransform: "uppercase",
  flex: "0 0 auto",
};

const cacheMetaStyle: CSSProperties = {
  minWidth: 0,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  color: "var(--text-secondary)",
  fontSize: "0.73rem",
  textTransform: "none",
};

const orderedChipStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "5px 8px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.76rem",
};

const dragHandleStyle: CSSProperties = {
  color: "var(--text-tertiary)",
  cursor: "grab",
  fontWeight: 700,
  letterSpacing: 0,
  userSelect: "none",
};

const miniButtonStyle: CSSProperties = {
  minHeight: "24px",
  padding: "2px 7px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-inset)",
  color: "var(--text-secondary)",
  fontSize: "0.68rem",
  cursor: "pointer",
};

export const labelStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
  fontSize: "0.75rem",
  fontWeight: 600,
  textTransform: "uppercase",
  color: "var(--text-secondary)",
};

export const inputStyle: CSSProperties = {
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
