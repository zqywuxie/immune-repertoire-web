import { useEffect, useState } from "react";
import type { ScriptHubSourceContext } from "./index";
import type { GroupSpec } from "../../../shared/api/groupSpecs";

type Props = {
  projectId: string;
  sourceContext?: ScriptHubSourceContext;
  groupSpecs: GroupSpec[];
  loadingSpecs: boolean;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
};

const CHART_TYPES = [
  { key: "heatmap", label: "热力图 (Heatmap)" },
  { key: "treemap", label: "树图 (Treemap)" },
  { key: "chord", label: "弦图 (Chord)" },
];

export function ChartsCombinedForm({
  sourceContext,
  groupSpecs,
  loadingSpecs,
  value,
  onChange,
}: Props) {
  const sampleOptions = uniqueStrings(sourceContext?.sampleNames || []);
  const chainOptions = uniqueStrings(sourceContext?.chains || []);
  const selectedModules = stringList(value.selected_modules).length
    ? stringList(value.selected_modules)
    : ["heatmap", "treemap", "chord"];
  const selectedSamples = stringList(value.samples);
  const selectedChains = stringList(value.selected_chains).length
    ? stringList(value.selected_chains)
    : chainOptions;
  const [sampleCandidate, setSampleCandidate] = useState("");
  const [sampleFilter, setSampleFilter] = useState("");

  useEffect(() => {
    const next: Record<string, unknown> = { ...value };
    let changed = false;
    if (!Array.isArray(value.selected_modules)) {
      next.selected_modules = selectedModules;
      changed = true;
    }
    if (!Array.isArray(value.selected_chains) && chainOptions.length) {
      next.selected_chains = chainOptions;
      changed = true;
    }
    if (changed) onChange(next);
  }, [chainOptions.join("\n")]);

  const setField = (k: string, v: unknown) => onChange({ ...value, [k]: v });

  const toggleChart = (key: string) => {
    const next = selectedModules.includes(key)
      ? selectedModules.filter((item) => item !== key)
      : [...selectedModules, key];
    setField("selected_modules", next);
  };

  const toggleChain = (chain: string) => {
    const next = selectedChains.includes(chain)
      ? selectedChains.filter((item) => item !== chain)
      : [...selectedChains, chain];
    setField("selected_chains", next);
  };

  const addSample = () => {
    if (!sampleCandidate) return;
    setField("samples", uniqueStrings([...selectedSamples, sampleCandidate]));
    setSampleCandidate("");
  };

  const visibleSamples = sampleOptions.filter((sample) => sample.toLowerCase().includes(sampleFilter.trim().toLowerCase()));
  const availableSamples = visibleSamples.filter((sample) => !selectedSamples.includes(sample));
  const selectSamples = (samples: string[]) => setField("samples", uniqueStrings(samples));
  const selectVisible = () => selectSamples([...selectedSamples, ...visibleSamples]);
  const onlyVisible = () => selectSamples(visibleSamples);
  const invertVisible = () => selectSamples([
    ...selectedSamples.filter((sample) => !visibleSamples.includes(sample)),
    ...visibleSamples.filter((sample) => !selectedSamples.includes(sample)),
  ]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
      <Section title="Chart Types">
        <ChipGrid
          items={CHART_TYPES}
          selected={selectedModules}
          onToggle={toggleChart}
        />
      </Section>

      <Section title="Samples">
        {sampleOptions.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-sm)" }}>
            <input
              value={sampleFilter}
              onChange={(event) => setSampleFilter(event.target.value)}
              placeholder="Filter samples by keyword"
              style={inputSelectStyle}
            />
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto auto", gap: "var(--spacing-xs)" }}>
              <select value={sampleCandidate} onChange={(event) => setSampleCandidate(event.target.value)} style={inputSelectStyle}>
                <option value="">{availableSamples.length ? "Select sample" : "All detected samples selected"}</option>
                {availableSamples.map((sample) => (
                  <option key={sample} value={sample}>{sample}</option>
                ))}
              </select>
              <button type="button" onClick={addSample} disabled={!sampleCandidate} style={buttonStyle(Boolean(sampleCandidate))}>
                Add
              </button>
              <button type="button" onClick={() => setField("samples", [])} disabled={!selectedSamples.length} style={buttonStyle(Boolean(selectedSamples.length), false)}>
                Clear
              </button>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
              <button type="button" onClick={() => selectSamples(sampleOptions)} disabled={!sampleOptions.length} style={buttonStyle(Boolean(sampleOptions.length))}>
                All
              </button>
              <button type="button" onClick={selectVisible} disabled={!visibleSamples.length} style={buttonStyle(Boolean(visibleSamples.length))}>
                Select visible
              </button>
              <button type="button" onClick={onlyVisible} disabled={!visibleSamples.length} style={buttonStyle(Boolean(visibleSamples.length))}>
                Only visible
              </button>
              <button type="button" onClick={invertVisible} disabled={!visibleSamples.length} style={buttonStyle(Boolean(visibleSamples.length), false)}>
                Invert visible
              </button>
              <button type="button" onClick={() => selectSamples(sampleOptions.slice(0, 20))} disabled={!sampleOptions.length} style={buttonStyle(Boolean(sampleOptions.length), false)}>
                First 20
              </button>
            </div>
            {selectedSamples.length ? (
              <RemovableChips
                values={selectedSamples}
                onRemove={(sample) => setField("samples", selectedSamples.filter((item) => item !== sample))}
              />
            ) : (
              <div style={hintStyle}>请选择需要处理的样本；空选择不会主动提交全量样本。</div>
            )}
          </div>
        ) : (
          <div style={hintStyle}>No samples detected from the selected PEP assets.</div>
        )}
      </Section>

      <Section title="Chains">
        {chainOptions.length ? (
          <ChipGrid
            items={chainOptions.map((chain) => ({ key: chain, label: chain }))}
            selected={selectedChains}
            onToggle={toggleChain}
          />
        ) : (
          <div style={hintStyle}>No chains detected from the selected PEP assets.</div>
        )}
      </Section>

      <FormField label="Group Spec">
        <select
          value={(value.group_spec_id as string) || ""}
          onChange={(e) => setField("group_spec_id", e.target.value || undefined)}
          disabled={loadingSpecs}
          style={inputSelectStyle}
        >
          <option value="">Profile fields / none</option>
          {groupSpecs.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </FormField>
    </div>
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

function ChipGrid({
  items,
  selected,
  onToggle,
}: {
  items: Array<{ key: string; label: string }>;
  selected: string[];
  onToggle: (key: string) => void;
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
      {items.map((item) => {
        const active = selected.includes(item.key);
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => onToggle(item.key)}
            style={{
              padding: "6px 10px",
              borderRadius: "var(--radius-pill)",
              border: "1px solid var(--separator)",
              background: active ? "var(--accent)" : "var(--bg-elevated)",
              color: active ? "#fff" : "var(--text-primary)",
              cursor: "pointer",
              fontSize: "0.8rem",
              fontWeight: 600,
            }}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

function RemovableChips({
  values,
  onRemove,
}: {
  values: string[];
  onRemove: (value: string) => void;
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
      {values.map((value) => (
        <button
          key={value}
          type="button"
          onClick={() => onRemove(value)}
          title="Remove sample"
          style={{
            padding: "5px 10px",
            borderRadius: "var(--radius-pill)",
            border: "1px solid var(--accent)",
            background: "color-mix(in srgb, var(--accent) 10%, transparent)",
            color: "var(--text-primary)",
            fontSize: "0.78rem",
            cursor: "pointer",
          }}
        >
          {value} x
        </button>
      ))}
    </div>
  );
}

function FormField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        fontSize: "0.75rem",
        fontWeight: 600,
        textTransform: "uppercase",
        color: "var(--text-secondary)",
      }}
    >
      {label}
      {children}
    </label>
  );
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item || "").trim()).filter(Boolean) : [];
}

function uniqueStrings(value: string[]) {
  return Array.from(new Set(value.map((item) => String(item || "").trim()).filter(Boolean)));
}

function buttonStyle(active: boolean, primary = true): React.CSSProperties {
  return {
    minHeight: "38px",
    padding: "0 12px",
    borderRadius: "var(--radius-control)",
    border: "1px solid var(--separator)",
    background: active && primary ? "var(--accent)" : "var(--bg-inset)",
    color: active && primary ? "#fff" : "var(--text-secondary)",
    cursor: active ? "pointer" : "not-allowed",
    fontSize: "0.78rem",
    fontWeight: 600,
  };
}

const hintStyle: React.CSSProperties = {
  padding: "8px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-inset)",
  color: "var(--text-secondary)",
  fontSize: "0.78rem",
};

const inputSelectStyle: React.CSSProperties = {
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
