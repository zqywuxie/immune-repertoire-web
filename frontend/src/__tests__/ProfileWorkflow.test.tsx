import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { AssetUpload } from "../features/assets/AssetUpload";
import { Stage4Execution } from "../features/scripthub/stages/Stage4Execution";
import * as scriptHub from "../shared/api/scriptHub";

vi.mock("../shared/api/projects", async (importOriginal) => ({
  ...await importOriginal<typeof import("../shared/api/projects")>(),
  listProjectAssets: vi.fn().mockResolvedValue({ assets: [] }),
}));

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("Profile upload and analysis", () => {
  it("uploads the actual Profile file without requiring PEP", async () => {
    const file = new File(["sample,group,metric\nS1,A,1\nS2,B,2"], "profile.csv", { type: "text/csv" });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ assets: [{ id: "asset-1" }] }) });
    vi.stubGlobal("fetch", fetchMock);
    const saved = vi.fn();
    render(<AssetUpload projectId="project-1" onSuccess={saved} />);
    fireEvent.change(screen.getByLabelText("上传 样本指标表（CSV / TSV / Excel）", { selector: "input" }), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "保存数据" }));
    await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
    const [url, options] = fetchMock.mock.calls.find(([url]) => url === "/api/projects/project-1/assets")!;
    expect(url).toBe("/api/projects/project-1/assets");
    expect(options.body).toBeInstanceOf(FormData);
    const uploaded = options.body.get("files") as File;
    expect(uploaded.name).toBe(file.name);
    expect(uploaded.size).toBe(file.size);
    expect(await new Promise((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(uploaded); })).toBe("sample,group,metric\nS1,A,1\nS2,B,2");
    expect(options.body.get("asset_type")).toBe("profile");
    expect(options.body.get("asset_set")).toBe("Set1");
    expect(screen.getByText(/已保存 1 个文件/)).toBeInTheDocument();
  });

  it("retains the selected file and reports a failed upload", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, statusText: "Bad Request", json: async () => ({ message: "文件格式错误" }) }));
    const saved = vi.fn();
    render(<AssetUpload projectId="project-1" onSuccess={saved} />);
    fireEvent.change(screen.getByLabelText("上传 样本指标表（CSV / TSV / Excel）", { selector: "input" }), {
      target: { files: [new File(["invalid"], "profile.csv")] },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存数据" }));
    await waitFor(() => expect(screen.getByText(/文件格式错误/)).toBeInTheDocument());
    expect(screen.getByText("profile.csv")).toBeInTheDocument();
    expect(saved).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "保存数据" })).toBeEnabled();
  });

  it("waits for the real task result and retains CSV and PNG outputs", async () => {
    const submit = vi.spyOn(scriptHub, "submitLegacyScriptHubJob").mockResolvedValue({ success: true, job_id: "task-1", task_id: "task-1", status: "queued" });
    vi.spyOn(scriptHub, "getLegacyScriptHubTask")
      .mockResolvedValueOnce({ success: true, job_id: "task-1", task_id: "task-1", status: "queued" })
      .mockResolvedValue({ success: true, job_id: "task-1", task_id: "task-1", module: "profile", status: "completed", result: {
        viewer_url: "/report/viewer.html", png_urls: ["/report/metric.png"], csv_urls: ["/report/metric.csv"], zip_url: "/report/results.zip",
      } });
    const complete = vi.fn();
    const running = vi.fn();
    render(<Stage4Execution projectId="project-1" modules={["profile"]} baseConfig={{ profile_path: "/uploaded/profile.csv", asset_set: "Set2" }}
      moduleConfigs={{ profile: { grouptype_fields: ["group"], selected_group_values: { group: ["A", "B"] }, selected_samples_by_group: { group: { A: ["S1"], B: ["S2"] } }, param_begin: "metric", param_over: "metric" } }} jobIds={[]}
      onJobsCreated={vi.fn()} onComplete={complete} onRunningChange={running} />);
    fireEvent.click(screen.getByRole("button", { name: /Run Analysis|开始分析/ }));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(complete).not.toHaveBeenCalled();
    expect(running).toHaveBeenCalledWith(true);
    expect(submit.mock.calls[0][0]).toMatchObject({ module: "profile", projectId: "project-1", payload: { profile_path: "/uploaded/profile.csv", asset_set: "Set2", grouptype_fields: ["group"] } });
    await waitFor(() => expect(complete).toHaveBeenCalledTimes(1), { timeout: 4000 });
    const result = complete.mock.calls[0][0]["task-1"];
    expect(result.status).toBe("completed");
    expect(result.outputs.map((output: { url: string }) => output.url)).toEqual(expect.arrayContaining(["/report/metric.csv", "/report/metric.png"]));
    expect(running).toHaveBeenLastCalledWith(false);
  });

  it("does not substitute detected columns for an explicit group selection", async () => {
    const submit = vi.spyOn(scriptHub, "submitLegacyScriptHubJob");
    render(<Stage4Execution projectId="project-1" modules={["profile"]}
      baseConfig={{ group_fields: ["group", "metric"] }} moduleConfigs={{ profile: { param_begin: "metric", param_over: "metric" } }}
      jobIds={[]} onJobsCreated={vi.fn()} onComplete={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Run Analysis|开始分析/ }));
    await waitFor(() => expect(screen.getByText(/请选择分组字段/)).toBeInTheDocument());
    expect(submit).not.toHaveBeenCalled();
  });
});
