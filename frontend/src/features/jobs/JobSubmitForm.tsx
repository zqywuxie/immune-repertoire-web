import { useState } from "react";
import { Send } from "lucide-react";
import { submitJob, getJobResults, type JobResultsResponse } from "../../shared/api/jobs";
import type { JobModule } from "../../shared/types/domain";

const defaultPayload = JSON.stringify(
  {
    selected_modules: ["heatmap", "treemap", "chord"],
    samples: [],
    selected_chains: [],
    field_mapping: {},
  },
  null,
  2
);

type Props = {
  modules: JobModule[];
  projectId: string;
  onJobSubmitted?: (jobId: string) => void;
  onResultLoaded?: (result: JobResultsResponse) => void;
};

export function JobSubmitForm({
  modules,
  projectId,
  onJobSubmitted,
  onResultLoaded,
}: Props) {
  const [module, setModule] = useState(
    modules[0]?.key || "charts.combined"
  );
  const [payloadText, setPayloadText] = useState(defaultPayload);
  const [forceRerun, setForceRerun] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");

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
          <p
            style={{
              margin: "2px 0 0",
              fontSize: "0.8rem",
              color: "var(--text-secondary)",
            }}
          >
            Unified API bridge
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

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(180px, 1fr) auto",
          gap: "var(--spacing-md)",
          alignItems: "end",
        }}
      >
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
          Module
          <select
            value={module}
            onChange={(e) => setModule(e.target.value)}
            disabled={state === "loading"}
            style={{
              minHeight: "38px",
              padding: "7px 10px",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--separator)",
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
            }}
          >
            {(modules.length ? modules : [{ key: module, label: module }]).map(
              (m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              )
            )}
          </select>
        </label>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            fontSize: "0.85rem",
            cursor: "pointer",
            paddingBottom: "4px",
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
