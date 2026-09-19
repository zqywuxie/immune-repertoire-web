import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { apiClient } from "../shared/api/client";
import { getJob } from "../shared/api/jobs";
import { statisticalPayload } from "../shared/api/statistical";
import { uploadDataFile } from "../shared/api/files";
import { useJobResult } from "../shared/hooks/useJobResult";

const response = (data: unknown, status = 200) => ({ ok: status < 400, status, statusText: "request failed", headers: new Headers({ "content-type": "application/json" }), json: async () => data });
afterEach(() => { cleanup(); apiClient.invalidateCache(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("statistical workflow", () => {
  it("uploads a File body before using the returned server id", async () => {
    const fetch = vi.fn().mockResolvedValue(response({ id: "server-id", name: "data.csv", columns: ["arm", "value"], row_count: 6 }));
    vi.stubGlobal("fetch", fetch);
    const file = new File(["arm,value\nA,1\nB,2"], "data.csv");
    const uploaded = await uploadDataFile(file, "project-1");
    const body = fetch.mock.calls[0][1].body as FormData;
    expect(fetch.mock.calls[0][0]).toContain("/api/files/upload");
    expect((body.get("file") as File).size).toBe(file.size);
    expect(body.get("project")).toBe("project-1");
    expect(statisticalPayload([uploaded], "value", "arm", "statistics")).toEqual({ module: "statistical.analyze", payload: { file_id: "server-id", value_column: "value", group_column: "arm" } });
    expect(statisticalPayload([uploaded, { ...uploaded, id: "second", name: "second.csv" }], "value", "arm", "boxplot").payload).toMatchObject({ files: [{ file_id: "server-id", name: "data.csv" }, { file_id: "second", name: "second.csv" }] });
  });
  it("blocks missing fields and repeated dataset names", () => {
    const file = { id: "1", name: "data.csv", columns: ["arm", "value"], row_count: 4 };
    expect(() => statisticalPayload([file], "absent", "arm", "statistics")).toThrow("所选字段");
    expect(() => statisticalPayload([file, { ...file, id: "2" }], "value", "arm", "statistics")).toThrow("名称重复");
  });
  it("reads fresh status and recovers from a previously rejected request", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response({}, 404)).mockResolvedValueOnce(response({ job: { status: "running" } })).mockResolvedValueOnce(response({ job: { status: "completed" } }));
    vi.stubGlobal("fetch", fetch);
    await expect(getJob("retry-test")).rejects.toThrow();
    expect((await getJob("retry-test")).job.status).toBe("running");
    expect((await getJob("retry-test")).job.status).toBe("completed");
    expect(fetch).toHaveBeenCalledTimes(3);
  });
  it("waits for completion before fetching results and stops on unmount", async () => {
    const urls: string[] = [];
    let polls = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      urls.push(url);
      if (url.endsWith("/results")) return response({ success: true, status: "completed", job: { status: "completed" }, result: { data: { results: {} } }, outputs: [], assets: [] });
      return response({ job: { status: ++polls === 1 ? "queued" : "completed" } });
    }));
    const hook = renderHook(() => useJobResult("poll-test"));
    await waitFor(() => expect(polls).toBe(1));
    expect(urls.some(url => url.endsWith("/results"))).toBe(false);
    await waitFor(() => expect(hook.result.current.status).toBe("completed"), { timeout: 3500 });
    expect(hook.result.current.result?.status).toBe("completed");
    hook.unmount();
    expect(urls.filter(url => url.endsWith("/results"))).toHaveLength(1);
  });
  it("discards a late response when the selected job changes", async () => {
    let resolveOld!: (value: unknown) => void;
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/old") ? new Promise(resolve => { resolveOld = resolve; }) : Promise.resolve(response({ job: { status: "failed", error: "new job failed" } }))));
    const hook = renderHook(({ id }) => useJobResult(id), { initialProps: { id: "old" } });
    hook.rerender({ id: "new" });
    await waitFor(() => expect(hook.result.current.error).toBe("new job failed"));
    await act(async () => { resolveOld(response({ job: { status: "completed" } })); });
    expect(hook.result.current.jobId).toBe("new");
    expect(hook.result.current.error).toBe("new job failed");
  });
});
