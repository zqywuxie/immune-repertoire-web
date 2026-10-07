import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../shared/api/client";
import { submitJob } from "../shared/api/jobs";
import { submitAnalysisBatch, submitLegacyScriptHubJob } from "../shared/api/scriptHub";

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Bad Request",
    headers: { get: () => "application/json" },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

const pendingValidation = {
  error: "VALIDATION_ERROR",
  message: "输入文件正在后台校验，请稍后重新检查。",
  details: { input_quality: { inputs: [{ kind: "profile", status: "pending" }] } },
};

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Script Hub waits for asynchronous input checks", () => {
  it("retries a legacy analysis submission only while validation is pending", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(pendingValidation, 400))
      .mockResolvedValueOnce(response({ success: true, job_id: "job-ready" }));
    vi.stubGlobal("fetch", fetchMock);

    const submitted = submitLegacyScriptHubJob({
      module: "profile",
      payload: { project_id: "project-1" },
      projectId: "project-1",
    });
    await vi.advanceTimersByTimeAsync(1000);

    await expect(submitted).resolves.toMatchObject({ job_id: "job-ready" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("also waits for pending validation on the current job API", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(pendingValidation, 400))
      .mockResolvedValueOnce(response({ success: true, job_id: "job-modern" }));
    vi.stubGlobal("fetch", fetchMock);

    const submitted = submitJob({
      module: "profile",
      payload: { project_id: "project-1" },
      projectId: "project-1",
    });
    await vi.advanceTimersByTimeAsync(1000);

    await expect(submitted).resolves.toMatchObject({ job_id: "job-modern" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry ordinary validation failures", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      error: "VALIDATION_ERROR",
      message: "缺少分组字段",
      details: { input_quality: { inputs: [{ kind: "profile", status: "invalid" }] } },
    }, 400));
    vi.stubGlobal("fetch", fetchMock);

    await expect(submitAnalysisBatch("project-1", "Set1", "batch", [
      { module: "profile", payload: { project_id: "project-1" } },
    ])).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
