import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../shared/api/client";
import { submitLegacyScriptHubJob } from "../shared/api/scriptHub";

describe("PEP optional step payload", () => {
  afterEach(() => vi.restoreAllMocks());

  it("preserves selected clone tracking, category heatmap, database alignment, and V/J summary steps", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ job_id: "job-test" } as never);

    await submitLegacyScriptHubJob({
      module: "pep-analysis",
      payload: { optional_steps: ["12", "11", "10", "9", "unsupported"] },
    });

    expect(post).toHaveBeenCalledWith("/api/script-hub/jobs", expect.objectContaining({
      optional_steps: ["12", "11", "10", "9"],
      module: "pep-analysis",
    }));
  });

  it("preserves an explicit choice to skip all optional steps", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ job_id: "job-test" } as never);

    await submitLegacyScriptHubJob({
      module: "pep-analysis",
      payload: { optional_steps: [] },
    });

    expect(post).toHaveBeenCalledWith("/api/script-hub/jobs", expect.objectContaining({
      optional_steps: [],
    }));
  });
});
