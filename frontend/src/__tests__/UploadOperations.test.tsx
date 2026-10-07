import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ProjectDatasetManager } from "../features/assets/ProjectDatasetManager";
import { AssetUpload } from "../features/assets/AssetUpload";
import { apiClient } from "../shared/api/client";
import * as projects from "../shared/api/projects";
import { createUploadOperationId, UploadResponseUnknownError } from "../shared/api/uploadOperations";
import type { ProjectAsset } from "../shared/types/domain";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); apiClient.invalidateCache(); });
const asset = { id: "saved", project_id: "p", asset_type: "profile", original_name: "指标.csv", storage_path: "/synthetic/profile.csv", size: 1 } as ProjectAsset;
const file = () => new File(["sample,value\n001,1"], "指标.csv");
const operationId = "dc976d27-b421-411f-8b12-ecc8080522c6";

it("上传成功但响应中断时，核对真实保存记录后返回成功", async () => {
  const fetchMock = vi.fn().mockRejectedValue(new TypeError("connection lost"));
  vi.stubGlobal("fetch", fetchMock);
  const get = vi.spyOn(apiClient, "get").mockResolvedValue({ saved: true, assets: [asset] });
  const checking = vi.fn();
  const result = await projects.uploadProjectAssets("p", { assetType: "profile", files: [file()], operationId, onStatusCheck: checking });
  expect(result.assets[0].id).toBe("saved");
  expect((fetchMock.mock.calls[0][1].body as FormData).get("operation_id")).toBe(operationId);
  expect(get).toHaveBeenCalledWith(`/api/projects/p/upload-operations/${operationId}`, undefined, { skipCache: true });
  expect(checking).toHaveBeenCalledTimes(1);
});

it("重试先核对已保存操作，不再次传输文件", async () => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(apiClient, "get").mockResolvedValue({ saved: true, assets: [asset] });
  expect((await projects.uploadProjectAssets("p", { assetType: "profile", files: [file()], operationId, retry: true })).assets).toEqual([asset]);
  expect(fetchMock).not.toHaveBeenCalled();
});

it("核对尚未确认时，保留未知状态而不声称未保存", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("lost")));
  vi.spyOn(apiClient, "get").mockResolvedValue({ saved: false, assets: [] });
  await expect(projects.uploadProjectAssets("p", { assetType: "profile", files: [file()], operationId })).rejects.toBeInstanceOf(UploadResponseUnknownError);
});

it("服务端明确拒绝输入时，直接展示错误而不当成响应中断", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ message: "文件校验未通过" }) }));
  const get = vi.spyOn(apiClient, "get");
  await expect(projects.uploadProjectAssets("p", { assetType: "profile", files: [file()], operationId })).rejects.toThrow("文件校验未通过");
  expect(get).not.toHaveBeenCalled();
});

it("浏览器XHR进度请求响应丢失后也会核对保存结果", async () => {
  const send = vi.fn();
  class LostRequest {
    upload = {}; withCredentials = false;
    onerror?: () => void;
    open = vi.fn(); abort = vi.fn();
    send(body: FormData) { send(body); queueMicrotask(() => this.onerror?.()); }
  }
  vi.stubGlobal("XMLHttpRequest", LostRequest);
  vi.spyOn(apiClient, "get").mockResolvedValue({ saved: true, assets: [asset] });
  const result = await projects.uploadProjectAssets("p", { assetType: "profile", files: [file()], operationId, onProgress: vi.fn() });
  expect(result.assets).toEqual([asset]);
  expect(send.mock.calls[0][0].get("operation_id")).toBe(operationId);
});

it("目录登记丢失响应后可恢复已保存记录", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("lost")));
  vi.spyOn(apiClient, "get").mockResolvedValue({ saved: true, assets: [{ ...asset, asset_type: "pep" }] });
  const result = await projects.registerProjectPath("p", { storagePath: "/synthetic/pep", assetSet: "甲", operationId });
  expect(result.id).toBe("saved");
});

it("上传队列未知项保留文件，重试沿用原操作标识", async () => {
  vi.spyOn(projects,"previewUploadImpact").mockImplementation(async (_id,items)=>({impacts:items.map(item=>({...item,assets:[],expected_versions:[],pagination:{page:1,page_size:20,total:0,total_pages:0}}))}));
  vi.spyOn(projects, "listProjectDatasets").mockResolvedValue({ datasets: [] });
  vi.spyOn(projects, "listProjectAssets").mockResolvedValue({ assets: [] });
  const upload = vi.spyOn(projects, "uploadProjectAssets").mockRejectedValueOnce(new UploadResponseUnknownError()).mockResolvedValueOnce({ assets: [asset] });
  const success = vi.fn();
  render(<AssetUpload projectId="p" initialAssetType="profile" onSuccess={success} />);
  fireEvent.change(screen.getByLabelText("上传样本指标表（逗号分隔、制表符分隔或表格文件）", { selector: "input" }), { target: { files: [file()] } });
  await waitFor(()=>expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "保存数据（1 项）" }));
  expect(await screen.findByText(/^保存状态待确认/)).toBeVisible();
  expect(screen.getByRole("button", { name: "从提交清单移除 指标.csv" })).toBeVisible();
  // Changing a pending option must not create a new identity after an unknown response.
  fireEvent.click(screen.getByRole("switch", { name: /更新当前版本/ }));
  await waitFor(()=>expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "保存数据（1 项）" }));
  await waitFor(() => expect(success).toHaveBeenCalledTimes(1));
  expect(upload.mock.calls[1][1].operationId).toBe(upload.mock.calls[0][1].operationId);
  expect(upload.mock.calls[0][1].retry).toBe(false);
  expect(upload.mock.calls[1][1].retry).toBe(true);
  expect(screen.queryByRole("button", { name: "从提交清单移除 指标.csv" })).not.toBeInTheDocument();
});

it("内网HTTP缺少randomUUID时仍生成有效的操作标识", () => {
  vi.stubGlobal("crypto", { getRandomValues: (values: Uint8Array) => { for (let i = 0; i < values.length; i++) values[i] = i; return values; } });
  expect(createUploadOperationId()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

it("未知上传已在原数据集保存时，修改数据集后不能误认当前范围保存成功", async () => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(apiClient, "get").mockResolvedValue({ saved: true, assets: [{ ...asset, metadata: {
    asset_set: "甲", upload_operation: { manifest: { kind: "files", asset_type: "profile", asset_set: "甲",
      replace_existing: false, files: [{ name: "指标.csv", relative_path: "指标.csv" }] } },
  } }] });
  await expect(projects.uploadProjectAssets("p", { assetType: "profile", files: [file()], operationId,
    retry: true, assetSet: "乙" })).rejects.toThrow("当前选项已改变");
  expect(fetchMock).not.toHaveBeenCalled();
});

it("直接打开指定数据集的导入地址，实际保存仍使用该数据集", async () => {
  vi.spyOn(projects, "listProjectDatasets").mockResolvedValue({ datasets: [] });
  vi.spyOn(projects, "listProjectAssets").mockResolvedValue({ assets: [] });
  const upload = vi.spyOn(projects, "uploadProjectAssets").mockResolvedValue({ assets: [asset] });
  render(<MemoryRouter initialEntries={["/?tab=assets&import=1&asset_set=甲"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()} /></MemoryRouter>);
  fireEvent.change(await screen.findByLabelText("上传样本指标表（逗号分隔、制表符分隔或表格文件）", { selector: "input" }), { target: { files: [file()] } });
  fireEvent.click(screen.getByRole("button", { name: "保存数据（1 项）" }));
  await waitFor(() => expect(upload).toHaveBeenCalledWith("p", expect.objectContaining({ assetSet: "甲" })));
});
