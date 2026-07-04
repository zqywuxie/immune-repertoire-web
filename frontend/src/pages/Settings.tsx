import { useState, useEffect } from "react";
import { Save, RotateCcw } from "lucide-react";
import { PageHeader } from "../shared/components/PageHeader";
import { Card } from "../shared/components/Card";

type Workspace = "management" | "analysis";

type SettingsData = {
  // Visualization
  colorScheme: string;
  figureWidth: number;
  figureHeight: number;
  fontSize: number;
  // Export
  exportDpi: number;
  exportFormat: "png" | "svg" | "pdf";
  // Chart
  barWidth: number;
  barSpacing: number;
  showValues: boolean;
  // Heatmap
  showAnnotations: boolean;
  vmin: number | null;
  vmax: number | null;
};

const DEFAULTS: Record<Workspace, SettingsData> = {
  management: {
    colorScheme: "default",
    figureWidth: 800,
    figureHeight: 600,
    fontSize: 12,
    exportDpi: 150,
    exportFormat: "png",
    barWidth: 0.7,
    barSpacing: 0.2,
    showValues: true,
    showAnnotations: true,
    vmin: null,
    vmax: null,
  },
  analysis: {
    colorScheme: "viridis",
    figureWidth: 1000,
    figureHeight: 700,
    fontSize: 13,
    exportDpi: 300,
    exportFormat: "png",
    barWidth: 0.8,
    barSpacing: 0.15,
    showValues: false,
    showAnnotations: true,
    vmin: null,
    vmax: null,
  },
};

export function Settings() {
  // Determine workspace from route
  const workspace: Workspace = window.location.pathname.startsWith("/management") ? "management" : "analysis";

  const [settings, setSettings] = useState<SettingsData>(() => {
    const stored = localStorage.getItem(`ir-settings-${workspace}`);
    if (stored) {
      try { return { ...DEFAULTS[workspace], ...JSON.parse(stored) }; } catch { /* fall through */ }
    }
    return { ...DEFAULTS[workspace] };
  });

  const [saved, setSaved] = useState(false);

  // Persist to localStorage
  useEffect(() => {
    localStorage.setItem(`ir-settings-${workspace}`, JSON.stringify(settings));
  }, [settings, workspace]);

  // Also sync to backend if available
  const handleSave = async () => {
    try {
      const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
      await fetch(`${API_BASE}/api/settings?workspace=${workspace}`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
    } catch {
      // Backend may not support settings yet — localStorage fallback is fine
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleReset = () => {
    setSettings({ ...DEFAULTS[workspace] });
  };

  const update = <K extends keyof SettingsData>(key: K, value: SettingsData[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <>
      <PageHeader
        title={`${workspace === "management" ? "Management" : "Analysis"} Settings`}
        subtitle="Configure visualization, export, and chart preferences"
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(360px, 100%), 1fr))", gap: "var(--spacing-lg)" }}>
        {/* Main settings area */}
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
          {/* Visualization Settings */}
          <Card>
            <h3 style={{ margin: "0 0 var(--spacing-md)" }}>Visualization Settings</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(240px, 100%), 1fr))", gap: "var(--spacing-md)" }}>
              <Field label="Color Scheme">
                <select value={settings.colorScheme} onChange={(e) => update("colorScheme", e.target.value)} className="select">
                  <option value="default">Default</option>
                  <option value="viridis">Viridis</option>
                  <option value="plasma">Plasma</option>
                  <option value="inferno">Inferno</option>
                  <option value="magma">Magma</option>
                  <option value="cividis">Cividis</option>
                </select>
              </Field>
              <Field label="Figure Width (px)">
                <input type="number" value={settings.figureWidth} onChange={(e) => update("figureWidth", Number(e.target.value))} className="input" min={400} max={2000} />
              </Field>
              <Field label="Figure Height (px)">
                <input type="number" value={settings.figureHeight} onChange={(e) => update("figureHeight", Number(e.target.value))} className="input" min={300} max={2000} />
              </Field>
              <Field label="Font Size">
                <input type="number" value={settings.fontSize} onChange={(e) => update("fontSize", Number(e.target.value))} className="input" min={8} max={24} />
              </Field>
            </div>
          </Card>

          {/* Export Settings */}
          <Card>
            <h3 style={{ margin: "0 0 var(--spacing-md)" }}>Export Settings</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(240px, 100%), 1fr))", gap: "var(--spacing-md)" }}>
              <Field label="DPI">
                <select value={settings.exportDpi} onChange={(e) => update("exportDpi", Number(e.target.value))} className="select">
                  <option value={72}>72 (web)</option>
                  <option value={150}>150 (screen)</option>
                  <option value={300}>300 (print)</option>
                  <option value={600}>600 (high-res)</option>
                </select>
              </Field>
              <Field label="Format">
                <select value={settings.exportFormat} onChange={(e) => update("exportFormat", e.target.value as SettingsData["exportFormat"])} className="select">
                  <option value="png">PNG</option>
                  <option value="svg">SVG</option>
                  <option value="pdf">PDF</option>
                </select>
              </Field>
            </div>
          </Card>

          {/* Chart Settings */}
          <Card>
            <h3 style={{ margin: "0 0 var(--spacing-md)" }}>Chart Settings</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(240px, 100%), 1fr))", gap: "var(--spacing-md)" }}>
              <Field label="Bar Width">
                <input type="number" value={settings.barWidth} onChange={(e) => update("barWidth", Number(e.target.value))} className="input" min={0.1} max={1} step={0.05} />
              </Field>
              <Field label="Bar Spacing">
                <input type="number" value={settings.barSpacing} onChange={(e) => update("barSpacing", Number(e.target.value))} className="input" min={0} max={0.5} step={0.05} />
              </Field>
              <Field label="Show Values">
                <input type="checkbox" checked={settings.showValues} onChange={(e) => update("showValues", e.target.checked)} style={{ width: "auto", marginTop: "8px" }} />
              </Field>
            </div>
          </Card>

          {/* Heatmap Settings */}
          <Card>
            <h3 style={{ margin: "0 0 var(--spacing-md)" }}>Heatmap Settings</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(240px, 100%), 1fr))", gap: "var(--spacing-md)" }}>
              <Field label="Show Annotations">
                <input type="checkbox" checked={settings.showAnnotations} onChange={(e) => update("showAnnotations", e.target.checked)} style={{ width: "auto", marginTop: "8px" }} />
              </Field>
              <Field label="Vmin">
                <input type="number" value={settings.vmin ?? ""} onChange={(e) => update("vmin", e.target.value ? Number(e.target.value) : null)} className="input" placeholder="Auto" />
              </Field>
              <Field label="Vmax">
                <input type="number" value={settings.vmax ?? ""} onChange={(e) => update("vmax", e.target.value ? Number(e.target.value) : null)} className="input" placeholder="Auto" />
              </Field>
            </div>
          </Card>

          {/* Actions */}
          <div style={{ display: "flex", gap: "var(--spacing-md)", justifyContent: "flex-end" }}>
            <button onClick={handleReset} className="btn btn-secondary">
              <RotateCcw size={16} />
              Reset Defaults
            </button>
            <button onClick={handleSave} className="btn btn-primary">
              <Save size={16} />
              {saved ? "Saved!" : "Save Settings"}
            </button>
          </div>
        </div>

        {/* Summary sidebar */}
        <div>
          <Card>
            <h3 style={{ margin: "0 0 var(--spacing-md)" }}>Current Config</h3>
            <dl style={{ fontSize: "0.82rem", lineHeight: 1.8 }}>
              <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Color</dt>
              <dd style={{ margin: "0 0 var(--spacing-sm)", color: "var(--text-primary)" }}>{settings.colorScheme}</dd>
              <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Dimensions</dt>
              <dd style={{ margin: "0 0 var(--spacing-sm)", color: "var(--text-primary)" }}>{settings.figureWidth} × {settings.figureHeight}px</dd>
              <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Export</dt>
              <dd style={{ margin: "0 0 var(--spacing-sm)", color: "var(--text-primary)" }}>{settings.exportDpi} DPI, {settings.exportFormat.toUpperCase()}</dd>
              <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Workspace</dt>
              <dd style={{ margin: 0, color: "var(--text-primary)" }}>{workspace}</dd>
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field-label">
      {label}
      {children}
    </label>
  );
}
