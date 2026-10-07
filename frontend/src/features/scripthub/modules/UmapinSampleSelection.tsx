import { ChipPicker, SamplePicker, Section, stringList } from "./shared";

export function UmapinSampleSelection({ groups, value, onChange, title = "投影样本范围", sampleLabel = "投影样本", description = "按当前特征表的分组和真实样本编号选择。跨批次同名样本按独立编号显示，可分别选择。" }: {
  description?: string;
  title?: string;
  sampleLabel?: string;
  groups: Record<string, string[]>;
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const categories = Object.keys(groups);
  const chosenCategories = Array.isArray(value.selected_categories) ? stringList(value.selected_categories) : categories;
  const samples = chosenCategories.flatMap(group => groups[group] || []);
  const chosenSamples = Array.isArray(value.selected_samples) ? stringList(value.selected_samples) : samples;
  const labels = Object.fromEntries(chosenCategories.flatMap(group => (groups[group] || []).map(sample => {
    const parts = sample.split("::");
    let label = sample;
    if (parts.length === 2) {
      try { label = parts.map(decodeURIComponent).join(" / "); } catch { /* Preserve source identifiers. */ }
    }
    return [sample, `${group} / ${label}`];
  })));
  return <Section title={title}>
    <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 0 }}>{description}</p>
    <ChipPicker label="纳入分组" selected={chosenCategories} options={categories.map(group => ({ key: group, label: `${group} (${groups[group].length})` }))}
      onToggle={next => onChange({ ...value, selected_categories: next })} />
    <SamplePicker value={value} setField={(key, next) => onChange({ ...value, [key]: next })}
      samples={samples} selectedSamples={chosenSamples} sampleLabels={labels} label={sampleLabel}
      onSelectedSamplesChange={next => onChange({ ...value, selected_samples: next })} />
  </Section>;
}
