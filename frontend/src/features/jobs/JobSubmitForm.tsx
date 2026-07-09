import { useState, useMemo } from "react";
import { Send, Code, FormInput } from "lucide-react";
import { submitJob, getJobResults, type JobResultsResponse } from "../../shared/api/jobs";
import type { JobModule } from "../../shared/types/domain";
import type { GroupSpec } from "../../shared/api/groupSpecs";
import { getFormComponent } from "./forms";

const DEFAULT_PAYLOAD = JSON.stringify(
  { selected_modules: ["heatmap", "treemap", "chord"] },
  null,
  2
);

type Props = {
  modules: JobModule[];
  projectId: string;
  groupSpecs: GroupSpec[];
  loadingSpecs: boolean;
  onJobSubmitted?: (jobId: string) => void;
  onResultLoaded?: (result: JobResultsResponse) => void;
};

export function JobSubmitForm({
  modules,
  projectId,
  groupSpecs,
  loadingSpecs,
  onJobSubmitted,
  onResultLoaded,
}: Props) {
  const [module, setModule] = useState(modules[0]?.key || "charts.combined");
  const [payloadText, setPayloadText] = useState(DEFAULT_PAYLOAD);
  const [forceRerun, setForceRerun] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");
  const [viewMode, setViewMode] = useState<"json" | "form">("form");

  const selectedModule = useMemo(
    () => modules.find((m) => m.key === module),
    [modules, module]
  );

  const uiEntry = selectedModule?.ui_entry || "";
  const FormComponent = getFormComponent(uiEntry);

  // Group modules by category for the select dropdown
  const grouped = useMemo(() => {
    const map = new Map<string, JobModule[]>();
    for (const m of modules) {
      const cat = m.category || "Other";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(m);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [modules]);

  // Parse current payload for form components
  const currentPayload = useMemo(() => {
    try {
      const p = JSON.parse(payloadText || "{}");
      return p && typeof p === "object" && !Array.isArray(p) ? p : {};
    } catch {
      return {};
    }
  }, [payloadText]);

  const handleFormChange = (newValue: Record<string, unknown>) => {
    setPayloadText(JSON.stringify(newValue, null, 2));
  };

  const handleSubmit = async () => {
    if (!module) return;
    setState("loading");
    setMessage("");
    try {
      const parsed = JSON.parse(payloadText || "{}");
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("Payload must be a JSON object.");
      }
      const result = await submitJob({
        module,
        payload: parsed,
        projectId,
        forceRerun,
      });
      setState("idle");
      setMessage(
        result.reused_result
          ? `Reused cached result ${result.result_id || result.job_id}.`
          : `Submitted job ${result.job_id}.`
      );
      if (result.job_id) {
        onJobSubmitted?.(result.job_id);
        try {
          const jobResult = await getJobResults(result.job_id);
          onResultLoaded?.(jobResult);
        } catch {
          // result load is best-effort
        }
      }
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Submission failed");
    }
  };

  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        padding: "var(--spacing-xl)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-md)",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--spacing-md)",
        }}
      >
        <div>
          <h4 style={{ margin: 0 }}>Submit Job</h4>
          <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
            {uiEntry || "JSON"} mode
          </p>
        </div>
        <button
          disabled={state === "loading"}
          onClick={handleSubmit}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "10px 20px",
            borderRadius: "var(--radius-control)",
            background: "var(--accent)",
            color: "#ffffff",
            fontWeight: 500,
            opacity: state === "loading" ? 0.7 : 1,
          }}
        >
          <Send size={16} />
          {state === "loading" ? "Submitting…" : "Submit"}
        </button>
      </div>

      {/* Module selector + force rerun */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(180px, 1fr) auto",
          gap: "var(--spacing-md)",
          alignItems: "end",
        }}
      >
        <label style={labelStyle}>
          Module
          <select
            value={module}
            onChange={(e) => setModule(e.target.value)}
            disabled={state === "loading"}
            style={selectStyle}
          >
            {grouped.map(([cat, mods]) => (
              <optgroup key={cat} label={cat}>
                {mods.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.label}
                  </option>
                ))}
              </optgroup>
            ))}
            {modules.length === 0 && <option value={module}>{module}</option>}
          </select>
        </label>

        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "4px",
            fontSize: "0.85rem",
            cursor: "pointer",
            paddingBottom: "4px",
            color: "var(--text-secondary)",
          }}
        >
          <input
            type="checkbox"
            checked={forceRerun}
            onChange={(e) => setForceRerun(e.target.checked)}
          />
          Force rerun
        </label>
      </div>

      {/* Module info banner */}
      {selectedModule && (selectedModule.description || selectedModule.output_kinds?.length) && (
        <div
          style={{
            fontSize: "0.78rem",
            color: "var(--text-secondary)",
            display: "flex",
            gap: "var(--spacing-sm)",
            flexWrap: "wrap",
            padding: "var(--spacing-sm) var(--spacing-md)",
            background: "var(--bg-root)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          {selectedModule.description && <span>{selectedModule.description}</span>}
          {selectedModule.output_kinds?.length && (
            <span style={{ display: "flex", gap: "4px", alignItems: "center" }}>
              Outputs:{" "}
              {selectedModule.output_kinds!.map((k: string) => (
                <span
                  key={k}
                  style={{
                    fontSize: "0.68rem",
                    fontWeight: 500,
                    textTransform: "uppercase",
                    padding: "1px 6px",
                    borderRadius: "var(--radius-pill)",
                    background: "var(--bg-elevated)",
                    border: "1px solid var(--separator)",
                  }}
                >
                  {k}
                </span>
              ))}
            </span>
          )}
        </div>
      )}

      {/* View mode toggle */}
      <div style={{ display: "flex", gap: "var(--spacing-xs)" }}>
        <button
          type="button"
          onClick={() => setViewMode("form")}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            padding: "4px 12px",
            borderRadius: "var(--radius-pill)",
            background: viewMode === "form" ? "var(--bg-elevated)" : "transparent",
            border: viewMode === "form" ? "1px solid var(--separator)" : "1px solid transparent",
            color: viewMode === "form" ? "var(--text-primary)" : "var(--text-tertiary)",
            fontSize: "0.75rem",
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          <FormInput size={14} />
          {FormComponent ? uiEntry : "Form"}
        </button>
        <button
          type="button"
          onClick={() => setViewMode("json")}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            padding: "4px 12px",
            borderRadius: "var(--radius-pill)",
            background: viewMode === "json" ? "var(--bg-elevated)" : "transparent",
            border: viewMode === "json" ? "1px solid var(--separator)" : "1px solid transparent",
            color: viewMode === "json" ? "var(--text-primary)" : "var(--text-tertiary)",
            fontSize: "0.75rem",
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          <Code size={14} />
          Raw JSON
        </button>
      </div>

      {/* Content area */}
      {viewMode === "form" && FormComponent ? (
        <FormComponent
          projectId={projectId}
          module={selectedModule?.key || module}
          groupSpecs={groupSpecs}
          loadingSpecs={loadingSpecs}
          value={currentPayload}
          onChange={handleFormChange}
        />
      ) : (
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
          Payload JSON
          <textarea
            value={payloadText}
            onChange={(e) => setPayloadText(e.target.value)}
            disabled={state === "loading"}
            spellCheck={false}
            style={{
              minHeight: "150px",
              padding: "12px",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--separator)",
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
              fontFamily: '"Cascadia Code", "Consolas", monospace',
              fontSize: "0.82rem",
              lineHeight: 1.5,
              resize: "vertical",
            }}
          />
        </label>
      )}

      {message && (
        <p
          style={{
            margin: 0,
            fontSize: "0.85rem",
            color: state === "error" ? "var(--danger)" : "var(--success)",
          }}
        >
          {message}
        </p>
      )}
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
  fontSize: "0.75rem",
  fontWeight: 600,
  textTransform: "uppercase",
  color: "var(--text-secondary)",
};

const selectStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
};
