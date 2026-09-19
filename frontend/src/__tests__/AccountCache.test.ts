import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../shared/api/client";
afterEach(() => { vi.unstubAllGlobals(); apiClient.invalidateCache(); });
function response(value: unknown) { return new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } }); }
describe("账号缓存隔离", () => {
  it("退出后不让上一账号的迟到响应重新写入缓存", async () => {
    let resolveOld!: (response: Response) => void;
    const fetchMock = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { resolveOld = resolve; })).mockResolvedValue(response({ owner: "new" }));
    vi.stubGlobal("fetch", fetchMock);
    const pending = apiClient.get("/api/projects");
    apiClient.invalidateCache();
    resolveOld(response({ owner: "old" }));
    await pending;
    expect(await apiClient.get("/api/projects")).toEqual({ owner: "new" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
