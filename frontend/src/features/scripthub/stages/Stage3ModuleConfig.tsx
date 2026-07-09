import { useEffect, useState, useMemo } from "react";
import {
  Layers,
  Check,
  X,
  Zap,
  AlertTriangle,
} from "lucide-react";
import { useApi } from "../../../shared/hooks/useApi";
import { listGroupSpecs } from "../../../shared/api/groupSpecs";
import type { JobModule } from "../../../shared/types/domain";
import { Card } from "../../../shared/components/Card";
import { getFormComponent } from "../../jobs/forms";
import type { ScriptHubSourceContext } from "../../jobs/forms";
import type { GroupSpec } from "../../../shared/api/groupSpecs";
import { assetLabel, getModuleAvailability } from "../moduleRequirements";

interface Stage3ModuleConfigProps {
  modules: JobModule[];
  projectId: string;
  selectedModules: string[];
  moduleConfigs: Record<string, Record<string, unknown>>;
  sourceContext?: ScriptHubSourceContext;
  onUpdate: (selectedModules: string[], moduleConfigs: Record<string, Record<string, unknown>>) => void;
}

export function Stage3ModuleConfig({
  modules,
  projectId,
  selectedModules,
  moduleConfigs,
  sourceContext,
  onUpdate,
}: Stage3ModuleConfigProps) {
  const [activeConfigKey, setActiveConfigKey] = useState<string | null>(selectedModules[0] || null);

  const allModules = modules;

  const groupSpecsState = useApi(
    () => projectId ? listGroupSpecs(projectId) : Promise.resolve({ group_specs: [] as GroupSpec[] }),
    [projectId],
  );
  const groupSpecs = groupSpecsState.status === "ready" ? groupSpecsState.data.group_specs : [];
  const loadingSpecs = groupSpecsState.status === "loading";

  useEffect(() => {
    if (!selectedModules.length) return;
    const validSelected = selectedModules.filter((key) => {
      const mod = allModules.find((item) => item.key === key);
      return getModuleAvailability(mod, sourceContext).selectable;
    });
    if (validSelected.length !== selectedModules.length) {
      const nextConfigs = Object.fromEntries(
        validSelected.map((key) => [key, moduleConfigs[key] || {}]),
      );
      onUpdate(validSelected, nextConfigs);
    }
    if (activeConfigKey && !validSelected.includes(activeConfigKey)) {
      setActiveConfigKey(null);
    }
  }, [allModules, activeConfigKey, selectedModules, moduleConfigs, sourceContext?.pepPaths?.join("|"), sourceContext?.profilePath, sourceContext?.transcriptomePath]);

  const groupedModules = useMemo(() => {
    const map = new Map<string, JobModule[]>();
    for (const m of allModules) {
      const cat = m.category || "Other";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(m);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [allModules]);

  const handleSelectModule = (key: string) => {
    const mod = allModules.find((item) => item.key === key);
    if (!getModuleAvailability(mod, sourceContext).selectable) return;
    const alreadySelected = selectedModules.includes(key);
    setActiveConfigKey(key);
    if (!alreadySelected) {
      onUpdate([...selectedModules, key], {
        ...moduleConfigs,
        [key]: moduleConfigs[key] || {},
      });
    }
  };

  const handleRemoveModule = (key: string) => {
    const nextSelected = selectedModules.filter((item) => item !== key);
    const nextConfigs = { ...moduleConfigs };
    delete nextConfigs[key];
    if (activeConfigKey === key) {
      setActiveConfigKey(nextSelected[0] || null);
    }
    onUpdate(nextSelected, nextConfigs);
  };

  const activeModule = allModules.find((m) => m.key === activeConfigKey);
  const ConfigForm = activeModule?.ui_entry
    ? getFormComponent(activeModule.ui_entry)
    : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
      {/* Header */}
      <div>
        <h2 style={{ margin: 0 }}>Stage 3: Module Configuration</h2>
        <p
          style={{
            margin: "4px 0 0",
            color: "var(--text-secondary)",
            fontSize: "0.875rem",
          }}
        >
          Select and configure the analysis modules to run. {allModules.length > 0 && `${allModules.length} modules available.`}
        </p>
      </div>

      {/* Module Grid */}
      {groupedModules.length === 0 ? (
        <div
          style={{
            padding: "var(--spacing-3xl)",
            textAlign: "center",
            color: "var(--text-tertiary)",
            background: "var(--bg-elevated)",
            borderRadius: "var(--radius-card)",
            border: "1px solid var(--separator)",
          }}
        >
          No analysis modules available.
        </div>
      ) : (
        groupedModules.map(([category, mods]) => (
          <div key={category}>
            <div
              style={{
                fontSize: "0.72rem",
                fontWeight: 600,
                textTransform: "uppercase",
                color: "var(--text-tertiary)",
                letterSpacing: "0.05em",
                marginBottom: "var(--spacing-sm)",
              }}
            >
              {category}
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                gap: "var(--spacing-sm)",
              }}
            >
              {mods.map((mod) => {
                const isActive = activeConfigKey === mod.key;
                const isSelected = selectedModules.includes(mod.key);
                const availability = getModuleAvailability(mod, sourceContext);
                const unavailable = !availability.selectable;
                return (
                  <div
                    key={mod.key}
                    onClick={() => handleSelectModule(mod.key)}
                    title={availability.reason || undefined}
                    style={{
                      padding: "var(--spacing-md) var(--spacing-lg)",
                      borderRadius: "var(--radius-control)",
                      border: isActive
                        ? "2px solid var(--accent)"
                        : isSelected
                          ? "1px solid rgba(0, 113, 227, 0.45)"
                        : "1px solid var(--separator)",
                      background: isActive
                        ? "rgba(0, 113, 227, 0.04)"
                        : isSelected
                          ? "rgba(0, 113, 227, 0.025)"
                        : "var(--bg-elevated)",
                      cursor: unavailable ? "not-allowed" : "pointer",
                      opacity: unavailable ? 0.55 : 1,
                      transition: "all var(--duration-fast) ease-out",
                      boxShadow: isActive ? "var(--shadow-md)" : "none",
                    }}
                  >
                    {/* Header row */}
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "var(--spacing-sm)",
                        marginBottom: "var(--spacing-xs)",
                      }}
                    >
                      <div
                        style={{
                          width: "32px",
                          height: "32px",
                          borderRadius: "var(--radius-control)",
                          background: isActive ? "var(--accent)" : "var(--bg-inset)",
                          color: isActive ? "#fff" : "var(--text-secondary)",
                          display: "grid",
                          placeItems: "center",
                          flexShrink: 0,
                        }}
                      >
                          {unavailable ? <AlertTriangle size={15} /> : isSelected ? <Check size={16} /> : <Layers size={16} />}
                      </div>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: "0.85rem",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {mod.label}
                        </div>
                        {mod.description && (
                          <div
                            style={{
                              fontSize: "0.7rem",
                              color: "var(--text-tertiary)",
                              marginTop: "2px",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              display: "-webkit-box",
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: "vertical",
                            }}
                          >
                            {mod.description}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Status badges */}
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "var(--spacing-xs)",
                        flexWrap: "wrap",
                        marginTop: "var(--spacing-sm)",
                      }}
                    >
                      {isSelected && (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleRemoveModule(mod.key);
                          }}
                          style={{
                            border: "1px solid rgba(0,113,227,0.25)",
                            background: "rgba(0,113,227,0.08)",
                            color: "var(--accent)",
                            borderRadius: "var(--radius-pill)",
                            padding: "2px 8px",
                            fontSize: "0.65rem",
                            cursor: "pointer",
                          }}
                        >
                          selected ×
                        </button>
                      )}
                      {mod.ui_entry && (
                        <span
                          style={{
                            fontSize: "0.65rem",
                            padding: "2px 6px",
                            borderRadius: "var(--radius-pill)",
                            background: "var(--bg-inset)",
                            color: "var(--text-secondary)",
                          }}
                        >
                          configurable
                        </span>
                      )}
                      {mod.output_kinds && mod.output_kinds.length > 0 && (
                        <span
                          style={{
                            fontSize: "0.65rem",
                            padding: "2px 6px",
                            borderRadius: "var(--radius-pill)",
                            background: "var(--bg-inset)",
                            color: "var(--text-secondary)",
                          }}
                        >
                          {mod.output_kinds.length} outputs
                        </span>
                      )}
                      {availability.missing.map((asset) => (
                        <span
                          key={asset}
                          style={{
                            fontSize: "0.65rem",
                            padding: "2px 6px",
                            borderRadius: "var(--radius-pill)",
                            background: "rgba(255,59,48,0.08)",
                            color: "var(--danger)",
                            border: "1px solid rgba(255,59,48,0.18)",
                          }}
                        >
                          Missing {assetLabel(asset)}
                        </span>
                      ))}
                      {isActive && (
                        <span
                          style={{
                            fontSize: "0.65rem",
                            padding: "2px 6px",
                            borderRadius: "var(--radius-pill)",
                            background: "var(--accent)",
                            color: "#fff",
                          }}
                        >
                          configuring
                        </span>
                      )}
                    </div>
                    {availability.reason && (
                      <div style={{ marginTop: "var(--spacing-xs)", fontSize: "0.7rem", color: "var(--danger)", lineHeight: 1.35 }}>
                        {availability.reason}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}

      {/* Configuration Panel */}
      {activeConfigKey && ConfigForm && activeModule && (
        <div
          style={{
            background: "var(--bg-elevated)",
            borderRadius: "var(--radius-panel)",
            border: "2px solid var(--accent)",
            padding: "var(--spacing-lg)",
            boxShadow: "var(--shadow-md)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "var(--spacing-md)",
              flexWrap: "wrap",
              gap: "var(--spacing-sm)",
            }}
          >
            <div>
              <h4 style={{ margin: 0, fontSize: "0.95rem" }}>{activeModule.label} Configuration</h4>
              {activeModule.description && (
                <p style={{ margin: "4px 0 0", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                  {activeModule.description}
                </p>
              )}
            </div>
            <button
              onClick={() => setActiveConfigKey(null)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
                padding: "6px 14px",
                borderRadius: "var(--radius-pill)",
                border: "1px solid var(--separator)",
                background: "var(--bg-elevated)",
                color: "var(--text-secondary)",
                fontSize: "0.75rem",
                cursor: "pointer",
              }}
            >
              <X size={14} /> Close
            </button>
          </div>
          <ConfigForm
            projectId={projectId}
            module={activeConfigKey}
            sourceContext={sourceContext}
            groupSpecs={groupSpecs}
            loadingSpecs={loadingSpecs}
            value={moduleConfigs[activeConfigKey] || {}}
            onChange={(v) => onUpdate(selectedModules, { ...moduleConfigs, [activeConfigKey]: v })}
          />
        </div>
      )}

      {/* Summary */}
      {selectedModules.length > 0 && (
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)" }}>
            <Zap size={18} style={{ color: "var(--accent)", flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                Ready to Execute
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                Selected modules: {selectedModules
                  .map((key) => allModules.find((m) => m.key === key)?.label || key)
                  .join(", ")}
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
