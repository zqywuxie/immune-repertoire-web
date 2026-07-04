import { beforeEach, describe, expect, it, vi } from "vitest";
import { getFormComponent } from "../features/jobs/forms";
import { listScriptHubModules } from "../shared/api/scriptHub";

const legacyModules = [
  "db-alignment",
  "boxplot",
  "profile",
  "topclone",
  "pep-analysis",
  "pgen-analysis",
  "umap",
  "volcano",
  "go-kegg-enrichment",
  "umapin",
  "ml-analysis",
  "mait-nkt",
  "charts",
];

describe("ScriptHub module registry", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("maps legacy ScriptHub modules to registered React form components", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      success: true,
      modules: legacyModules.map((key) => ({ key, label: key, status: "available" })),
    }), { status: 200, headers: { "content-type": "application/json" } })));

    const response = await listScriptHubModules();
    const modules = new Map(response.modules.map((module) => [module.key, module]));

    for (const key of legacyModules) {
      const uiEntry = modules.get(key)?.ui_entry;
      expect(uiEntry, key).toBeTruthy();
      expect(getFormComponent(uiEntry!), key).toBeTruthy();
    }

    expect(modules.get("charts")?.status).toBe("available");
    expect(modules.get("charts")?.ui_entry).toBe("ChartsCombinedForm");
    expect(modules.get("charts")?.execution_mode).toBe("job");
  });
});
