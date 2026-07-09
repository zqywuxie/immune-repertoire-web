import { useState, useCallback } from "react";
import { Download, Pencil, Users, AlertTriangle, Search, ChevronDown, ChevronRight } from "lucide-react";
import { useApi } from "../../shared/hooks/useApi";
import {
  listSamples,
  updateSample,
  exportSamplesUrl,
} from "../../shared/api/samples";
import type { SampleRecord, SampleUpdatePayload, ListSamplesParams } from "../../shared/api/samples";
import { PageHeader } from "../../shared/components/PageHeader";
import { Skeleton, SkeletonRow } from "../../shared/components/Skeleton";
import { EmptyState } from "../../shared/components/EmptyState";
import { Sheet } from "../../shared/components/Sheet";

const PAGE_SIZE = 50;

export function SampleRegistry() {
  const [filters, setFilters] = useState<ListSamplesParams>({});
  const [editSample, setEditSample] = useState<SampleRecord | null>(null);
  const [searchText, setSearchText] = useState("");

  const samples = useApi(() => listSamples(filters), [filters]);

  const sampleList = samples.status === "ready" ? samples.data.samples : [];
  const loading = samples.status === "loading";
  const error = samples.status === "error" ? samples.error : null;

  const filteredSamples = searchText
    ? sampleList.filter((s) => {
        const q = searchText.toLowerCase();
        return (
          (s.sample_id || "").toLowerCase().includes(q) ||
          (s.sample_name || "").toLowerCase().includes(q) ||
          (s.project_name || "").toLowerCase().includes(q)
        );
      })
    : sampleList;

  const handleFilterChange = (key: keyof ListSamplesParams, value: string) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (value === "" || value === undefined) {
        delete next[key];
      } else {
        (next as Record<string, string>)[key] = value;
      }
      return next;
    });
  };

  const handleClearFilters = () => {
    setFilters({});
    setSearchText("");
  };

  const handleExport = () => {
    window.open(exportSamplesUrl(filters), "_blank");
  };

  const handleSaveSample = useCallback(
    async (data: SampleUpdatePayload) => {
      if (!editSample) return;
      await updateSample(editSample.id, data);
      samples.refetch();
    },
    [editSample, samples]
  );

  const hasActiveFilters =
    !!filters.project_name ||
    !!filters.sample_id ||
    !!filters.chain_flag ||
    !!filters.is_healthy ||
    !!filters.spices ||
    !!filters.is_pe;

  return (
    <>
      <PageHeader title="Sample Registry" subtitle={`${filteredSamples.length} sample${filteredSamples.length !== 1 ? "s" : ""}`}>
        <button
          onClick={handleExport}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "10px 20px",
            borderRadius: "var(--radius-pill)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
            fontWeight: 500,
            fontSize: "0.875rem",
            cursor: "pointer",
          }}
        >
          <Download size={16} />
          Export CSV
        </button>
      </PageHeader>

      {/* Error banner */}
      {error && <ErrorBanner message={error} />}

      {/* Filter toolbar */}
      <FilterToolbar
        filters={filters}
        searchText={searchText}
        onFilterChange={handleFilterChange}
        onSearchChange={setSearchText}
        onClear={handleClearFilters}
        hasActiveFilters={hasActiveFilters || !!searchText}
      />

      {/* Sample table */}
      <SampleTable
        samples={filteredSamples}
        loading={loading}
        error={error}
        onEdit={setEditSample}
      />

      {/* Edit sample sheet */}
      {editSample && (
        <SampleEditSheet
          sample={editSample}
          open
          onClose={() => setEditSample(null)}
          onSave={handleSaveSample}
        />
      )}
    </>
  );
}

/* ── Filter Toolbar ─────────────────────────────────────────────────── */

function FilterToolbar({
  filters,
  searchText,
  onFilterChange,
  onSearchChange,
  onClear,
  hasActiveFilters,
}: {
  filters: ListSamplesParams;
  searchText: string;
  onFilterChange: (key: keyof ListSamplesParams, value: string) => void;
  onSearchChange: (v: string) => void;
  onClear: () => void;
  hasActiveFilters: boolean;
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  const hasAdvancedFilters =
    !!filters.sequence_id ||
    !!filters.institution ||
    !!filters.contain_method ||
    !!filters.iso_tag ||
    !!filters.spices ||
    !!filters.illness;

  const allHasActive = hasActiveFilters || hasAdvancedFilters || !!searchText;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-md)",
        marginBottom: "var(--spacing-lg)",
        padding: "var(--spacing-lg)",
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
      }}
    >
      {/* Basic filters row */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "var(--spacing-md)",
        }}
      >
        {/* Search input */}
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", flex: "1 1 240px", maxWidth: "320px" }}>
          <Search size={16} style={{ color: "var(--text-tertiary)", flexShrink: 0 }} />
          <input
            type="text"
            value={searchText}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search samples…"
            style={filterInputStyle}
            aria-label="Search samples"
          />
        </div>

        {/* Filter selects */}
        <FilterSelect
          label="Project"
          value={filters.project_name || ""}
          onChange={(v) => onFilterChange("project_name", v)}
        >
          <option value="">All projects</option>
        </FilterSelect>

        <FilterSelect
          label="Sample ID"
          value={filters.sample_id || ""}
          onChange={(v) => onFilterChange("sample_id", v)}
        >
          <option value="">All IDs</option>
        </FilterSelect>

        <FilterSelect
          label="Chain"
          value={filters.chain_flag || ""}
          onChange={(v) => onFilterChange("chain_flag", v)}
        >
          <option value="">All chains</option>
          <option value="TRA">TRA</option>
          <option value="TRB">TRB</option>
          <option value="TRG">TRG</option>
          <option value="TRD">TRD</option>
          <option value="IGH">IGH</option>
          <option value="IGK">IGK</option>
          <option value="IGL">IGL</option>
        </FilterSelect>

        <FilterSelect
          label="Health"
          value={filters.is_healthy || ""}
          onChange={(v) => onFilterChange("is_healthy", v)}
        >
          <option value="">All</option>
          <option value="yes">Healthy</option>
          <option value="no">Not healthy</option>
        </FilterSelect>

        <FilterSelect
          label="Species"
          value={filters.spices || ""}
          onChange={(v) => onFilterChange("spices", v)}
        >
          <option value="">All species</option>
          <option value="human">Human</option>
          <option value="mouse">Mouse</option>
          <option value="other">Other</option>
        </FilterSelect>

        <FilterSelect
          label="PE"
          value={filters.is_pe || ""}
          onChange={(v) => onFilterChange("is_pe", v)}
        >
          <option value="">All</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </FilterSelect>

        {allHasActive && (
          <button
            onClick={onClear}
            style={{
              padding: "6px 14px",
              borderRadius: "var(--radius-pill)",
              border: "1px solid var(--separator)",
              background: "var(--bg-elevated)",
              color: "var(--text-secondary)",
              fontSize: "0.8rem",
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Advanced filters toggle */}
      <div>
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            padding: 0,
            border: "none",
            background: "transparent",
            color: "var(--text-secondary)",
            fontSize: "0.8rem",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {showAdvanced ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          Advanced Filters
          {hasAdvancedFilters && (
            <span style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "18px",
              height: "18px",
              borderRadius: "50%",
              background: "var(--accent)",
              color: "#fff",
              fontSize: "0.65rem",
              fontWeight: 700,
            }}>
              •
            </span>
          )}
        </button>

        {showAdvanced && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: "var(--spacing-md)",
              marginTop: "var(--spacing-md)",
              paddingTop: "var(--spacing-md)",
              borderTop: "1px solid var(--separator)",
            }}
          >
            <FilterSelect
              label="Sequence ID"
              value={filters.sequence_id || ""}
              onChange={(v) => onFilterChange("sequence_id", v)}
            >
              <option value="">All</option>
            </FilterSelect>

            <FilterSelect
              label="Institution"
              value={filters.institution || ""}
              onChange={(v) => onFilterChange("institution", v)}
            >
              <option value="">All</option>
            </FilterSelect>

            <FilterSelect
              label="Contain Method"
              value={filters.contain_method || ""}
              onChange={(v) => onFilterChange("contain_method", v)}
            >
              <option value="">All</option>
            </FilterSelect>

            <FilterSelect
              label="ISO Tag"
              value={filters.iso_tag || ""}
              onChange={(v) => onFilterChange("iso_tag", v)}
            >
              <option value="">All</option>
            </FilterSelect>

            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              <label
                style={{
                  fontSize: "0.7rem",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  color: "var(--text-tertiary)",
                }}
              >
                Species (comma-sep)
              </label>
              <input
                type="text"
                value={filters.spices || ""}
                onChange={(e) => onFilterChange("spices", e.target.value)}
                placeholder="e.g. human,mouse"
                style={filterInputStyle}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              <label
                style={{
                  fontSize: "0.7rem",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  color: "var(--text-tertiary)",
                }}
              >
                Illness (comma-sep)
              </label>
              <input
                type="text"
                value={filters.illness || ""}
                onChange={(e) => onFilterChange("illness", e.target.value)}
                placeholder="e.g. healthy,influenza"
                style={filterInputStyle}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "2px",
        fontSize: "0.7rem",
        fontWeight: 600,
        textTransform: "uppercase",
        color: "var(--text-tertiary)",
        minWidth: "110px",
      }}
    >
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={filterSelectStyle}
      >
        {children}
      </select>
    </label>
  );
}

/* ── Sample Table ───────────────────────────────────────────────────── */

const SAMPLE_COLUMNS = [
  "Sample ID",
  "Name",
  "Project",
  "Chain",
  "Health",
  "Species",
  "Illness",
  "Sequence ID",
  "PE",
  "Institution",
  "Method",
  "Actions",
] as const;

function SampleTable({
  samples,
  loading,
  error,
  onEdit,
}: {
  samples: SampleRecord[];
  loading: boolean;
  error: string | null;
  onEdit: (sample: SampleRecord) => void;
}) {
  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Failed to load samples"
        description={error}
      />
    );
  }

  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        overflow: "auto",
      }}
    >
      <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "800px" }}>
        <thead>
          <tr style={{ background: "var(--bg-root)", borderBottom: "1px solid var(--separator)" }}>
            {SAMPLE_COLUMNS.map((h) => (
              <th
                key={h}
                scope="col"
                style={{
                  textAlign: "left",
                  padding: "12px 14px",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  color: "var(--text-secondary)",
                  whiteSpace: "nowrap",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <SkeletonRow columns={SAMPLE_COLUMNS.length} />
          ) : samples.length === 0 ? (
            <tr>
              <td
                colSpan={SAMPLE_COLUMNS.length}
                style={{
                  padding: "var(--spacing-3xl) var(--spacing-lg)",
                  textAlign: "center",
                  color: "var(--text-tertiary)",
                }}
              >
                No samples found. Try adjusting your filters.
              </td>
            </tr>
          ) : (
            samples.map((sample) => (
              <tr
                key={sample.id}
                style={{
                  borderBottom: "1px solid var(--separator)",
                  transition: "background var(--duration-fast)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--bg-inset)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "";
                }}
              >
                <td style={cellStyle}>
                  <code style={{ fontSize: "0.8rem", background: "var(--bg-inset)", padding: "2px 6px", borderRadius: "4px" }}>
                    {sample.sample_id || "—"}
                  </code>
                </td>
                <td style={{ ...cellStyle, maxWidth: "160px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {sample.sample_name}
                </td>
                <td style={cellStyle}>
                  {sample.project_name || "—"}
                </td>
                <td style={cellStyle}>
                  <span style={chipStyle}>{sample.chain_flag || "—"}</span>
                </td>
                <td style={cellStyle}>
                  <span
                    style={{
                      ...chipStyle,
                      background: sample.is_healthy === "yes" ? "rgba(52,199,89,0.12)" : sample.is_healthy === "no" ? "rgba(255,59,48,0.12)" : "var(--bg-inset)",
                      color: sample.is_healthy === "yes" ? "var(--success)" : sample.is_healthy === "no" ? "var(--danger)" : "var(--text-secondary)",
                    }}
                  >
                    {sample.is_healthy || "—"}
                  </span>
                </td>
                <td style={cellStyle}>{sample.spices || "—"}</td>
                <td style={{ ...cellStyle, maxWidth: "120px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {sample.illness || "—"}
                </td>
                <td style={cellStyle}>
                  <code style={{ fontSize: "0.8rem", background: "var(--bg-inset)", padding: "2px 6px", borderRadius: "4px" }}>
                    {sample.sequence_id || "—"}
                  </code>
                </td>
                <td style={cellStyle}>
                  <span style={chipStyle}>{sample.is_pe || "—"}</span>
                </td>
                <td style={{ ...cellStyle, maxWidth: "140px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {sample.institution || "—"}
                </td>
                <td style={cellStyle}>{sample.contain_method || "—"}</td>
                <td style={cellStyle}>
                  <button
                    onClick={() => onEdit(sample)}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px",
                      padding: "5px 10px",
                      borderRadius: "var(--radius-control)",
                      border: "1px solid var(--separator)",
                      background: "var(--bg-elevated)",
                      color: "var(--text-primary)",
                      fontSize: "0.8rem",
                      fontWeight: 500,
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                    }}
                  >
                    <Pencil size={14} />
                    Edit
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

/* ── Sample Edit Sheet ──────────────────────────────────────────────── */

function SampleEditSheet({
  sample,
  open,
  onClose,
  onSave,
}: {
  sample: SampleRecord;
  open: boolean;
  onClose: () => void;
  onSave: (data: SampleUpdatePayload) => Promise<void>;
}) {
  const [sampleName, setSampleName] = useState(sample.sample_name);
  const [chainFlag, setChainFlag] = useState(sample.chain_flag || "");
  const [isHealthy, setIsHealthy] = useState(sample.is_healthy || "");
  const [spices, setSpices] = useState(sample.spices || "");
  const [illness, setIllness] = useState(sample.illness || "");
  const [containMethod, setContainMethod] = useState(sample.contain_method || "");
  const [isoTag, setIsoTag] = useState(sample.iso_tag || "");
  const [sequenceId, setSequenceId] = useState(sample.sequence_id || "");
  const [institution, setInstitution] = useState(sample.institution || "");
  const [isPe, setIsPe] = useState(sample.is_pe || "");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const handleSave = async () => {
    setSaving(true);
    setSaveError("");
    try {
      await onSave({
        sample_name: sampleName.trim() || undefined,
        chain_flag: chainFlag || undefined,
        is_healthy: isHealthy || undefined,
        spices: spices || undefined,
        illness: illness || undefined,
        contain_method: containMethod || undefined,
        iso_tag: isoTag || undefined,
        sequence_id: sequenceId || undefined,
        institution: institution || undefined,
        is_pe: isPe || undefined,
      });
      onClose();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title="Edit Sample">
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
        {/* Read-only fields */}
        <ReadOnlyField label="Sample ID" value={sample.sample_id || "—"} />
        <ReadOnlyField label="Project" value={sample.project_name || "—"} />

        {/* Editable fields */}
        <Field label="Sample Name">
          <input
            type="text"
            value={sampleName}
            onChange={(e) => setSampleName(e.target.value)}
            style={editInputStyle}
          />
        </Field>

        <Field label="Sequence ID">
          <input
            type="text"
            value={sequenceId}
            onChange={(e) => setSequenceId(e.target.value)}
            style={editInputStyle}
          />
        </Field>

        <Field label="Chain Flag">
          <select value={chainFlag} onChange={(e) => setChainFlag(e.target.value)} style={editSelectStyle}>
            <option value="">— None —</option>
            <option value="TRA">TRA</option>
            <option value="TRB">TRB</option>
            <option value="TRG">TRG</option>
            <option value="TRD">TRD</option>
            <option value="IGH">IGH</option>
            <option value="IGK">IGK</option>
            <option value="IGL">IGL</option>
          </select>
        </Field>

        <Field label="Health Status">
          <select value={isHealthy} onChange={(e) => setIsHealthy(e.target.value)} style={editSelectStyle}>
            <option value="">— None —</option>
            <option value="yes">Healthy</option>
            <option value="no">Not healthy</option>
          </select>
        </Field>

        <Field label="PE (Paired-End)">
          <select value={isPe} onChange={(e) => setIsPe(e.target.value)} style={editSelectStyle}>
            <option value="">— None —</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </Field>

        <Field label="Species">
          <input
            type="text"
            value={spices}
            onChange={(e) => setSpices(e.target.value)}
            placeholder="e.g. human, mouse"
            style={editInputStyle}
          />
        </Field>

        <Field label="Illness">
          <input
            type="text"
            value={illness}
            onChange={(e) => setIllness(e.target.value)}
            placeholder="e.g. healthy, influenza"
            style={editInputStyle}
          />
        </Field>

        <Field label="Institution">
          <input
            type="text"
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
            placeholder="e.g. Tsinghua University"
            style={editInputStyle}
          />
        </Field>

        <Field label="Contain Method">
          <input
            type="text"
            value={containMethod}
            onChange={(e) => setContainMethod(e.target.value)}
            style={editInputStyle}
          />
        </Field>

        <Field label="ISO Tag">
          <input
            type="text"
            value={isoTag}
            onChange={(e) => setIsoTag(e.target.value)}
            style={editInputStyle}
          />
        </Field>

        {saveError && (
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--danger)" }}>
            {saveError}
          </p>
        )}

        <div style={{ display: "flex", gap: "var(--spacing-sm)", justifyContent: "flex-end" }}>
          <button onClick={onClose} disabled={saving} style={secondaryBtnStyle}>
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving} style={primaryBtnStyle}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </Sheet>
  );
}

/* ── Reusable helpers ───────────────────────────────────────────────── */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
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

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <span style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", color: "var(--text-secondary)" }}>
        {label}
      </span>
      <span style={{ fontSize: "0.85rem", color: "var(--text-primary)", padding: "7px 0" }}>
        {value}
      </span>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--spacing-sm)",
        padding: "var(--spacing-md) var(--spacing-lg)",
        borderRadius: "var(--radius-panel)",
        background: "var(--danger)",
        color: "#fff",
        fontSize: "0.85rem",
        fontWeight: 500,
        marginBottom: "var(--spacing-lg)",
      }}
    >
      <AlertTriangle size={18} />
      {message}
    </div>
  );
}

/* ── Styles ─────────────────────────────────────────────────────────── */

const cellStyle: React.CSSProperties = {
  padding: "10px 14px",
  fontSize: "0.85rem",
  color: "var(--text-primary)",
};

const chipStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 8px",
  borderRadius: "var(--radius-pill)",
  background: "var(--bg-inset)",
  fontSize: "0.75rem",
  color: "var(--text-secondary)",
};

const filterInputStyle: React.CSSProperties = {
  flex: 1,
  minHeight: "36px",
  padding: "6px 8px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
};

const filterSelectStyle: React.CSSProperties = {
  minHeight: "36px",
  padding: "5px 8px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.82rem",
  cursor: "pointer",
};

const editInputStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
};

const editSelectStyle: React.CSSProperties = {
  ...editInputStyle,
  cursor: "pointer",
};

const primaryBtnStyle: React.CSSProperties = {
  padding: "8px 20px",
  borderRadius: "var(--radius-control)",
  background: "var(--accent)",
  color: "#fff",
  fontWeight: 500,
  border: "none",
  cursor: "pointer",
};

const secondaryBtnStyle: React.CSSProperties = {
  ...primaryBtnStyle,
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  border: "1px solid var(--separator)",
};
