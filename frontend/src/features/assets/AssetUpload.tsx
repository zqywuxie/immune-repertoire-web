import { useEffect, useMemo, useState } from "react";
import { Upload, FolderTree, FileText, Database, Plus, Tag, Trash2, Layers, AlertTriangle } from "lucide-react";
import { listProjectAssets, uploadProjectAssets } from "../../shared/api/projects";
import { Toggle } from "../../shared/components/Toggle";
import { FileDropZone } from "../../shared/components/FileDropZone";
import { PathInput } from "../../shared/components/PathInput";
import { Select } from "../../shared/components/Select";
import { useApi } from "../../shared/hooks/useApi";
import { buildAssetSets, nextAssetSetName } from "./assetSets";
import type { AssetSet } from "./assetSets";

/* ── Data Set builder — PEP(s) + Profile + Transcriptome as a group ─── */

type Props = {
  projectId: string;
  onSuccess: () => void;
};

interface SetEntry {
  groupLabel: string;
  existingPepPaths: string[];
  existingProfilePath: string;
  existingTranscriptomePath: string;
  pepPaths: string[];
  profileFile: { name: string; size: number; file: File } | null;
  transcriptomeFile: { name: string; size: number; file: File } | null;
}

const emptySet = (): SetEntry => ({
  groupLabel: "Set1",
  existingPepPaths: [],
  existingProfilePath: "",
  existingTranscriptomePath: "",
  pepPaths: [],
  profileFile: null,
  transcriptomeFile: null,
});

const setFromExisting = (set?: AssetSet, fallbackName = "Set1"): SetEntry => ({
  ...emptySet(),
  groupLabel: set?.name || fallbackName,
  existingPepPaths: set?.pepPaths || [],
  existingProfilePath: set?.profilePath || "",
  existingTranscriptomePath: set?.transcriptomePath || "",
});

export function AssetUpload({ projectId, onSuccess }: Props) {
  const [sets, setSets] = useState<SetEntry[]>([emptySet()]);
  const [mode, setMode] = useState<"existing" | "new">("new");
  const [selectedSetName, setSelectedSetName] = useState("");
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");
  const [pepDrafts, setPepDrafts] = useState<Record<number, string>>({});

  const assetsState = useApi(() => listProjectAssets(projectId, { pageSize: 200 }), [projectId, message]);
  const existingSets = useMemo(
    () => buildAssetSets(assetsState.status === "ready" ? assetsState.data.assets : []),
    [assetsState],
  );
  const defaultNewSetName = useMemo(() => nextAssetSetName(existingSets), [existingSets]);
  const selectedExistingSet = useMemo(
    () => existingSets.find((set) => set.name === selectedSetName),
    [existingSets, selectedSetName],
  );

  useEffect(() => {
    if (mode === "existing" && !selectedSetName && existingSets.length > 0) {
      setSelectedSetName(existingSets[0].name);
    }
  }, [existingSets, mode, selectedSetName]);

  useEffect(() => {
    if (mode !== "existing") return;
    setPepDrafts({});
    setSets([setFromExisting(selectedExistingSet, selectedSetName || existingSets[0]?.name || "Set1")]);
  }, [
    mode,
    selectedSetName,
    selectedExistingSet?.name,
    selectedExistingSet?.pepPaths.join("|"),
    selectedExistingSet?.profilePath,
    selectedExistingSet?.transcriptomePath,
    existingSets.length,
  ]);

  useEffect(() => {
    if (
      mode === "new" &&
      sets.length === 1 &&
      sets[0].groupLabel !== defaultNewSetName &&
      (!sets[0].groupLabel || /^Set\d+$/i.test(sets[0].groupLabel))
    ) {
      setSets((prev) => prev.map((s, idx) => idx === 0 ? { ...s, groupLabel: defaultNewSetName } : s));
    }
  }, [defaultNewSetName, existingSets, mode, selectedSetName, sets]);

  const updateSet = (idx: number, patch: Partial<SetEntry>) => {
    setSets((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };

  const addSet = () => setSets((prev) => [...prev, { ...emptySet(), groupLabel: `Set${existingSets.length + prev.length + 1}` }]);
  const removeSet = (idx: number) => {
    setSets((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)));
    setPepDrafts({});
  };

  const updatePepDraft = (idx: number, value: string) => {
    setPepDrafts((prev) => ({ ...prev, [idx]: value }));
  };

  const addPepPath = (idx: number, rawPath: string) => {
    const path = rawPath.trim();
    if (!path) return;
    const target = sets[idx];
    if (!target || target.pepPaths.includes(path)) {
      setPepDrafts((prev) => ({ ...prev, [idx]: "" }));
      return;
    }
    updateSet(idx, { pepPaths: [...target.pepPaths, path] });
    setPepDrafts((prev) => ({ ...prev, [idx]: "" }));
  };

  const handleUpload = async () => {
    // Validate: analysis data sets require PEP + Profile. Transcriptome is optional.
    const validSets = sets.filter((s) => hasRequiredAnalysisData(s) && hasPendingAsset(s));
    if (validSets.length === 0) return;
    setState("loading");
    setMessage("");

    let uploaded = 0;
    let failed = 0;

    for (const [setIndex, s] of validSets.entries()) {
      const label = (mode === "existing" ? selectedSetName : s.groupLabel).trim() || `Set${setIndex + 1}`;

      try {
        // Register PEP paths — use /assets/register JSON endpoint
        for (const pepPath of s.pepPaths) {
          const registerBody: Record<string, unknown> = {
            asset_type: "pep",
            storage_path: pepPath.trim(),
            metadata_json: { asset_set: label, group_label: label },
          };
          const r = await fetch(`/api/projects/${projectId}/assets/register`, {
            method: "POST", credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(registerBody),
          });
          if (r.ok) uploaded++; else failed++;
        }
        // Upload Profile via FormData (metadata via separate register call)
        if (s.profileFile) {
          const result = await uploadProjectAssets(projectId, {
            assetType: "profile",
            files: [s.profileFile.file],
            replaceExisting,
            assetSet: label,
          });
          uploaded += result.assets.length;
        }
        // Upload Transcriptome
        if (s.transcriptomeFile) {
          const result = await uploadProjectAssets(projectId, {
            assetType: "transcriptome",
            files: [s.transcriptomeFile.file],
            replaceExisting,
            assetSet: label,
          });
          uploaded += result.assets.length;
        }
      } catch {
        failed++;
      }
    }

    setState("idle");
    setMessage(failed > 0
      ? `${uploaded} asset(s) registered, ${failed} failed.`
      : `${uploaded} asset(s) across ${validSets.length} data set(s) registered successfully.`);
    if (mode === "new") {
      setSets([{ ...emptySet(), groupLabel: nextAssetSetName(existingSets) }]);
    } else {
      setSets([setFromExisting(selectedExistingSet, selectedSetName || "Set1")]);
    }
    setPepDrafts({});
    onSuccess();
  };

  const invalidActiveSets = sets.filter((s) => hasPendingAsset(s) && !hasRequiredAnalysisData(s));
  const canSubmit =
    sets.some((s) => hasRequiredAnalysisData(s) && hasPendingAsset(s)) &&
    (mode === "new" || !!selectedSetName);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)", padding: "var(--spacing-xl)", background: "var(--bg-elevated)", borderRadius: "var(--radius-card)", border: "1px solid var(--separator)" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h4 style={{ margin: 0, fontSize: "0.95rem" }}>Register Data Set</h4>
          <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
            Each analysis set requires PEP paths + Profile. Transcriptome is optional.
          </p>
        </div>
        <StatusBadge status={state === "loading" ? "running" : state === "error" ? "failed" : "idle"} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(260px, 100%), 1fr))", gap: "var(--spacing-md)", alignItems: "end" }}>
        <label className="field-label">
          Set mode
          <Select
            value={mode}
            onChange={(value) => {
              const nextMode = value as "existing" | "new";
              setMode(nextMode);
              setPepDrafts({});
              if (nextMode === "new") {
                setSets([{ ...emptySet(), groupLabel: defaultNewSetName }]);
              } else {
                const nextName = selectedSetName || existingSets[0]?.name || "";
                setSelectedSetName(nextName);
                setSets([setFromExisting(existingSets.find((set) => set.name === nextName), nextName || "Set1")]);
              }
            }}
            disabled={state === "loading"}
            options={[
              { value: "new", label: "Create new set" },
              { value: "existing", label: "Update existing set" },
            ]}
          />
        </label>
        {mode === "existing" ? (
          <label className="field-label">
            Existing set
            <Select
              value={selectedSetName}
              onChange={(name) => {
                setSelectedSetName(name);
                setPepDrafts({});
                setSets([setFromExisting(existingSets.find((set) => set.name === name), name || "Set1")]);
              }}
              disabled={state === "loading" || existingSets.length === 0}
              placeholder={existingSets.length === 0 ? "No sets available" : "Select set"}
              options={existingSets.map((set) => ({
                value: set.name,
                label: `${set.name} · ${set.assets.length} asset${set.assets.length !== 1 ? "s" : ""}`,
              }))}
            />
          </label>
        ) : (
          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", paddingBottom: "10px" }}>
            New sets default to {defaultNewSetName}; names can be edited on each set card.
          </div>
        )}
      </div>

      {sets.map((s, idx) => (
        <div key={idx} style={{
          background: "var(--bg-root)", borderRadius: "var(--radius-panel)", border: "1px solid var(--separator)",
          padding: "var(--spacing-lg)", display: "flex", flexDirection: "column", gap: "var(--spacing-md)",
        }}>
          {/* Set header */}
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
              <Layers size={16} style={{ color: "var(--accent)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>
                {mode === "existing" ? `Current Set: ${selectedSetName || s.groupLabel}` : `Data Set ${idx + 1}`}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)" }}>
              {/* Group label */}
              <div style={{ display: "flex", alignItems: "center", gap: "4px", background: "var(--bg-elevated)", borderRadius: "var(--radius-pill)", border: "1px solid var(--separator)", padding: "3px 10px" }}>
                <Tag size={12} style={{ color: "var(--text-tertiary)" }} />
                <input
                  value={mode === "existing" ? selectedSetName : s.groupLabel}
                  onChange={(e) => updateSet(idx, { groupLabel: e.target.value })}
                  placeholder="Set name"
                  disabled={state === "loading" || mode === "existing"}
                  style={{ border: "none", outline: "none", background: "transparent", fontSize: "0.78rem", color: "var(--text-primary)", width: "120px", fontFamily: "var(--font-family)" }}
                />
              </div>
              {sets.length > 1 && (
                <button onClick={() => removeSet(idx)} style={iconBtn} title="Remove set" disabled={state === "loading"}>
                  <Trash2 size={14} style={{ color: "var(--danger)" }} />
                </button>
              )}
            </div>
          </div>

          {/* PEP Paths */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)", marginBottom: "var(--spacing-sm)" }}>
              <FolderTree size={14} style={{ color: "var(--accent)" }} />
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>PEP Paths</span>
              <span style={{ fontSize: "0.7rem", color: "var(--danger)" }}>(required · multiple supported)</span>
            </div>
            {mode === "existing" && (
              <ExistingPathList
                label="Current registered PEP paths"
                values={s.existingPepPaths}
                emptyLabel="No PEP path registered in this set."
              />
            )}
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "var(--spacing-sm)", alignItems: "start" }}>
              <PathInput
                value={pepDrafts[idx] || ""}
                onChange={(path) => updatePepDraft(idx, path)}
                onCommit={(path) => addPepPath(idx, path)}
                placeholder="/data/projects/.../pep_sample_dir/"
                disabled={state === "loading"}
                browsable
                hint="Browse or enter server directory paths. Press Enter or Add to register the path."
              />
              <button
                type="button"
                onClick={() => addPepPath(idx, pepDrafts[idx] || "")}
                disabled={state === "loading" || !(pepDrafts[idx] || "").trim()}
                className="btn btn-secondary"
                style={{ minHeight: "42px", padding: "8px 14px", whiteSpace: "nowrap" }}
              >
                <Plus size={14} />
                Add
              </button>
            </div>
            {s.pepPaths.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xs)", marginTop: "var(--spacing-sm)" }}>
                {mode === "existing" && <span style={subtleLabelStyle}>Pending PEP additions</span>}
                <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
                {s.pepPaths.map((p, pi) => (
                  <span key={pi} style={{
                    display: "inline-flex", alignItems: "center", gap: "4px",
                    padding: "3px 10px", borderRadius: "var(--radius-pill)",
                    background: "color-mix(in srgb, var(--accent) 10%, transparent)",
                    color: "var(--accent)", fontSize: "0.75rem", border: "1px solid color-mix(in srgb, var(--accent) 20%, transparent)",
                  }}>
                    <span style={{ maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p}>{p}</span>
                    <button onClick={() => updateSet(idx, { pepPaths: s.pepPaths.filter((_, i) => i !== pi) })} style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: "inherit" }}>
                      <Trash2 size={10} />
                    </button>
                  </span>
                ))}
                </div>
              </div>
            )}
          </div>

          {/* Profile */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)", marginBottom: "var(--spacing-sm)" }}>
              <FileText size={14} style={{ color: "var(--success)" }} />
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>Profile File</span>
              <span style={{ fontSize: "0.7rem", color: "var(--danger)" }}>(required)</span>
            </div>
            {mode === "existing" && (
              <ExistingPathLine
                label="Current registered Profile"
                value={s.existingProfilePath}
                emptyLabel="No Profile file registered in this set."
              />
            )}
            <FileDropZone
              files={s.profileFile ? [{ name: s.profileFile.name, size: s.profileFile.size, file: s.profileFile.file }] : []}
              onFilesAdded={(incoming) => {
                const f = Array.from(incoming as FileList)[0];
                if (f) updateSet(idx, { profileFile: { name: f.name, size: f.size, file: f } });
              }}
              onRemoveFile={() => updateSet(idx, { profileFile: null })}
              accept=".csv,.tsv,.csv.gz"
              multiple={false}
              disabled={state === "loading"}
              label={mode === "existing" && s.existingProfilePath ? "Drop a profile/datapoint CSV here to add or replace" : "Drop a profile/datapoint CSV here"}
            />
          </div>

          {/* Transcriptome */}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)", marginBottom: "var(--spacing-sm)" }}>
              <Database size={14} style={{ color: "var(--warning)" }} />
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>Transcriptome</span>
              <span style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>(optional)</span>
            </div>
            {mode === "existing" && (
              <ExistingPathLine
                label="Current registered Transcriptome"
                value={s.existingTranscriptomePath}
                emptyLabel="No Transcriptome file registered in this set."
              />
            )}
            <FileDropZone
              files={s.transcriptomeFile ? [{ name: s.transcriptomeFile.name, size: s.transcriptomeFile.size, file: s.transcriptomeFile.file }] : []}
              onFilesAdded={(incoming) => {
                const f = Array.from(incoming as FileList)[0];
                if (f) updateSet(idx, { transcriptomeFile: { name: f.name, size: f.size, file: f } });
              }}
              onRemoveFile={() => updateSet(idx, { transcriptomeFile: null })}
              accept=".csv,.tsv,.csv.gz,.xlsx"
              multiple={false}
              disabled={state === "loading"}
              label={mode === "existing" && s.existingTranscriptomePath ? "Drop an expression matrix here to add or replace" : "Drop an expression matrix here (optional)"}
            />
          </div>
        </div>
      ))}

      {/* Add set button */}
      {mode === "new" && <button onClick={addSet} disabled={state === "loading"} style={{
        display: "inline-flex", alignItems: "center", gap: "var(--spacing-sm)", padding: "8px 16px",
        borderRadius: "var(--radius-control)", border: "1px dashed var(--separator)", background: "transparent",
        color: "var(--text-secondary)", fontSize: "0.82rem", fontWeight: 500, cursor: "pointer", alignSelf: "flex-start",
      }}>
        <Plus size={15} /> Add Another Data Set
      </button>}

      {invalidActiveSets.length > 0 && (
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: "var(--spacing-sm)",
            padding: "var(--spacing-md)",
            borderRadius: "var(--radius-control)",
            border: "1px solid rgba(255,149,0,0.28)",
            background: "rgba(255,149,0,0.08)",
            color: "var(--warning)",
            fontSize: "0.82rem",
            lineHeight: 1.45,
          }}
        >
          <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: "2px" }} />
          <span>
            Analysis data set requires at least one PEP path and one Profile file. Transcriptome is optional.
          </span>
        </div>
      )}

      {/* Submit */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--separator)", paddingTop: "var(--spacing-md)" }}>
        <Toggle checked={replaceExisting} onChange={setReplaceExisting} disabled={state === "loading"} label="Replace existing" size="sm" />
        <button disabled={!canSubmit || state === "loading"} onClick={handleUpload} className="btn btn-primary" style={{ padding: "10px 24px" }}>
          <Upload size={15} />
          {state === "loading" ? "Registering…" : `Register ${sets.filter((s) => hasRequiredAnalysisData(s) && hasPendingAsset(s)).length} Set${sets.length !== 1 ? "s" : ""}`}
        </button>
      </div>

      {message && (
        <div style={{ padding: "var(--spacing-md) var(--spacing-lg)", borderRadius: "var(--radius-control)", background: state === "error" ? "rgba(255,59,48,0.08)" : "rgba(52,199,89,0.08)", border: `1px solid ${state === "error" ? "var(--danger)" : "var(--success)"}`, color: state === "error" ? "var(--danger)" : "var(--success)", fontSize: "0.85rem", fontWeight: 500 }}>{message}</div>
      )}
    </div>
  );
}

function hasPendingAsset(set: SetEntry): boolean {
  return set.pepPaths.length > 0 || Boolean(set.profileFile || set.transcriptomeFile);
}

function hasRequiredAnalysisData(set: SetEntry): boolean {
  const hasPep = set.existingPepPaths.length > 0 || set.pepPaths.length > 0;
  const hasProfile = Boolean(set.existingProfilePath || set.profileFile);
  return hasPep && hasProfile;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string; label: string }> = {
    idle: { bg: "var(--bg-inset)", text: "var(--text-tertiary)", label: "Ready" },
    running: { bg: "rgba(0,113,227,0.1)", text: "var(--accent)", label: "Working" },
    failed: { bg: "rgba(255,59,48,0.1)", text: "var(--danger)", label: "Error" },
  };
  const s = map[status] || map.idle;
  return <span style={{ padding: "3px 10px", borderRadius: "var(--radius-pill)", fontSize: "0.72rem", fontWeight: 600, background: s.bg, color: s.text }}>{s.label}</span>;
}

function ExistingPathList({
  label,
  values,
  emptyLabel,
}: {
  label: string;
  values: string[];
  emptyLabel: string;
}) {
  return (
    <div style={existingBlockStyle}>
      <span style={subtleLabelStyle}>{label}</span>
      {values.length ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
          {values.map((value) => (
            <span key={value} title={value} style={existingPathChipStyle}>
              {value}
            </span>
          ))}
        </div>
      ) : (
        <span style={emptyExistingStyle}>{emptyLabel}</span>
      )}
    </div>
  );
}

function ExistingPathLine({
  label,
  value,
  emptyLabel,
}: {
  label: string;
  value: string;
  emptyLabel: string;
}) {
  return (
    <div style={existingBlockStyle}>
      <span style={subtleLabelStyle}>{label}</span>
      {value ? (
        <span title={value} style={existingPathLineStyle}>{value}</span>
      ) : (
        <span style={emptyExistingStyle}>{emptyLabel}</span>
      )}
    </div>
  );
}

const iconBtn: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  width: "28px", height: "28px", borderRadius: "var(--radius-control)",
  border: "none", background: "transparent", cursor: "pointer",
};

const subtleLabelStyle: React.CSSProperties = {
  fontSize: "0.7rem",
  color: "var(--text-tertiary)",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const existingBlockStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "var(--spacing-xs)",
  marginBottom: "var(--spacing-sm)",
  padding: "var(--spacing-sm)",
  borderRadius: "var(--radius-control)",
  background: "var(--bg-elevated)",
  border: "1px solid var(--separator)",
};

const existingPathChipStyle: React.CSSProperties = {
  maxWidth: "260px",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  padding: "3px 9px",
  borderRadius: "var(--radius-pill)",
  background: "var(--bg-inset)",
  color: "var(--text-secondary)",
  fontSize: "0.73rem",
  fontFamily: '"SF Mono", "Cascadia Code", "Consolas", monospace',
};

const existingPathLineStyle: React.CSSProperties = {
  display: "block",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  color: "var(--text-secondary)",
  fontSize: "0.78rem",
  fontFamily: '"SF Mono", "Cascadia Code", "Consolas", monospace',
};

const emptyExistingStyle: React.CSSProperties = {
  color: "var(--text-tertiary)",
  fontSize: "0.78rem",
};
