import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter, MemoryRouter } from "react-router-dom";
import { SampleBatchSheet } from "../features/samples/SampleBatchSheet";
import { SampleRegistry } from "../pages/management/SampleRegistry";
import * as batch from "../shared/api/sampleBatch";
import * as projects from "../shared/api/projects";
import * as samples from "../shared/api/samples";
import { apiClient } from "../shared/api/client";
import type { SampleRecord } from "../shared/api/samples";

const viewport = vi.hoisted(() => ({ mobile: false }));
vi.mock("../shared/hooks/useMediaQuery", () => ({ useMediaQuery: () => viewport.mobile }));
const sample = {id:"r1",project_id:"p",project_name:"研究项目",sample_id:"001",sample_name:"样本一",extra_metadata:{asset_set:"甲"},
  sequence_id:null,spices:null,institution:null,chain_flag:null,is_healthy:null,illness:null,is_pe:null,contain_method:null,iso_tag:null,created_at:null,updated_at:null} satisfies SampleRecord;
function preview(rows = 1): batch.SampleBatchPreview {
  return {preview_token:"signed-preview",project_name:"研究项目",asset_set:"甲",counts:{update:rows},
    rows:Array.from({length:rows},(_,index)=>({row:index+1,sample_id:`00${index+1}`,record_id:`r${index+1}`,status:"update",message:"修改已有登记",linked:true,can_apply:true,
      changes:[{field:"illness",label:"疾病",before:"旧值",after:"新值"}]}))};
}
function sheet(records: SampleRecord[] = [sample], extra: Partial<Parameters<typeof SampleBatchSheet>[0]> = {}) {
  return render(<MemoryRouter><SampleBatchSheet initialProjectId="p" initialAssetSet="甲" selectedRecords={records} onClose={vi.fn()} onSaved={vi.fn()} onDraftChange={vi.fn()} {...extra}/></MemoryRouter>);
}
beforeEach(()=>{
  viewport.mobile=false;
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[{name:"甲",input_count:1,kinds:{}}]});
  vi.spyOn(projects,"listProjects").mockResolvedValue({projects:[{id:"p",name:"研究项目",status:"active"}],pagination:{page:1,page_size:20,total:1,total_pages:1}});
  vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"研究项目"} as never);
  vi.spyOn(samples,"getSampleFieldOptions").mockResolvedValue({fields:{}});
  vi.spyOn(samples,"listSamples").mockResolvedValue({samples:[sample],pagination:{page:1,page_size:50,total:1,total_pages:1}});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();apiClient.invalidateCache();});

it("所选批改先预览精确身份和新值，确认后才保存",async()=>{
  const inspect=vi.spyOn(batch,"previewSampleBatchRows").mockResolvedValue(preview());
  const save=vi.spyOn(batch,"applySampleBatch").mockResolvedValue({rows:[{row:1,sample_id:"001",status:"saved",message:"已保存"}],counts:{saved:1},asset_set:"甲"});
  const changed=vi.fn();sheet([sample],{onSaved:changed});
  fireEvent.change(screen.getByRole("textbox",{name:"批量字段新值"}),{target:{value:"新值"}});
  fireEvent.click(screen.getByRole("button",{name:"预览登记变更"}));
  await screen.findByRole("button",{name:"确认保存 1 条"});
  expect(inspect).toHaveBeenCalledWith("p","甲",[{record_id:"r1",sample_id:"001",fields:{illness:"新值"},clear_fields:[]}]);
  expect(save).not.toHaveBeenCalled();
  expect(screen.getByText("旧值")).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"确认保存 1 条"}));
  await waitFor(()=>expect(save).toHaveBeenCalledWith("p","signed-preview",[1]));
  expect(changed).toHaveBeenCalledTimes(1);
});

it("清空字段使用明确操作，不把空新值当作清空",async()=>{
  const inspect=vi.spyOn(batch,"previewSampleBatchRows").mockResolvedValue(preview());
  sheet();
  expect(screen.getByRole("button",{name:"预览登记变更"})).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox",{name:"明确清空此字段"}));
  expect(screen.getByRole("textbox",{name:"批量字段新值"})).toBeDisabled();
  fireEvent.click(screen.getByRole("button",{name:"预览登记变更"}));
  await waitFor(()=>expect(inspect).toHaveBeenCalledWith("p","甲",[{record_id:"r1",sample_id:"001",fields:{},clear_fields:["illness"]}]));
});

it("响应中断保留原预览并用同一身份核对重试",async()=>{
  vi.spyOn(batch,"previewSampleBatchRows").mockResolvedValue(preview());
  const save=vi.spyOn(batch,"applySampleBatch").mockRejectedValueOnce(new Error("连接中断")).mockResolvedValue({rows:[{row:1,sample_id:"001",status:"saved",message:"此前已保存",replayed:true}],counts:{saved:1},asset_set:"甲"});
  sheet();fireEvent.change(screen.getByRole("textbox",{name:"批量字段新值"}),{target:{value:"新值"}});
  fireEvent.click(screen.getByRole("button",{name:"预览登记变更"}));
  fireEvent.click(await screen.findByRole("button",{name:"确认保存 1 条"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("原预览已保留");
  fireEvent.click(screen.getByRole("button",{name:"核对并重试保存"}));
  await waitFor(()=>expect(screen.getByText("此前已保存")).toBeVisible());
  expect(save.mock.calls).toEqual([["p","signed-preview",[1]],["p","signed-preview",[1]]]);
});

it("部分失败只重试失败行，成功结果继续保留",async()=>{
  vi.spyOn(batch,"previewSampleBatchRows").mockResolvedValue(preview(2));
  const save=vi.spyOn(batch,"applySampleBatch").mockResolvedValueOnce({rows:[{row:1,sample_id:"001",status:"saved",message:"第一行已保存"},{row:2,sample_id:"002",status:"failed",message:"临时失败"}],counts:{saved:1,failed:1},asset_set:"甲"})
    .mockResolvedValueOnce({rows:[{row:2,sample_id:"002",status:"saved",message:"第二行已保存"}],counts:{saved:1},asset_set:"甲"});
  sheet([sample,{...sample,id:"r2",sample_id:"002"}]);
  fireEvent.change(screen.getByRole("textbox",{name:"批量字段新值"}),{target:{value:"新值"}});
  fireEvent.click(screen.getByRole("button",{name:"预览登记变更"}));
  fireEvent.click(await screen.findByRole("button",{name:"确认保存 2 条"}));
  fireEvent.click(await screen.findByRole("button",{name:"仅重试失败行"}));
  await waitFor(()=>expect(save).toHaveBeenLastCalledWith("p","signed-preview",[2]));
  expect(screen.getByText("第一行已保存")).toBeVisible();
  expect(await screen.findByText("第二行已保存")).toBeVisible();
  expect(screen.getByText("已处理 2 条 · 保存失败 0 条")).toBeVisible();
});

it("文件预览失败保留文件和补录选择，可原位重试",async()=>{
  const inspect=vi.spyOn(batch,"previewSampleBatchFile").mockRejectedValueOnce(new Error("临时读取失败")).mockResolvedValue(preview());
  sheet([]);const file=new File(["原始样本编号,疾病\n001,新值"],"登记.csv");
  fireEvent.change(screen.getByLabelText("上传批量登记表"),{target:{files:[file]}});
  fireEvent.click(screen.getByRole("checkbox",{name:"允许补充尚未关联输入的登记"}));
  fireEvent.click(screen.getByRole("button",{name:"预览登记变更"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("临时读取失败");
  expect(screen.getByText("登记.csv")).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"预览登记变更"}));
  await waitFor(()=>expect(inspect).toHaveBeenLastCalledWith("p","甲",file,true));
});

it("预览含无效行时返回逐行失败，不把成功行等同于全部完成",async()=>{
  const data=preview(2);data.rows[1]={...data.rows[1],status:"invalid",can_apply:false,message:"编号重复",changes:[]};data.counts={update:1,invalid:1};
  vi.spyOn(batch,"previewSampleBatchFile").mockResolvedValue(data);
  const save=vi.spyOn(batch,"applySampleBatch").mockResolvedValue({rows:[{row:1,sample_id:"001",status:"saved",message:"保存成功"},{row:2,sample_id:"002",status:"failed",message:"编号重复"}],counts:{saved:1,failed:1},asset_set:"甲"});
  sheet([]);fireEvent.change(screen.getByLabelText("上传批量登记表"),{target:{files:[new File(["data"],"登记.csv")]}});
  fireEvent.click(screen.getByRole("button",{name:"预览登记变更"}));
  fireEvent.click(await screen.findByRole("button",{name:"确认保存 1 条"}));
  await waitFor(()=>expect(save).toHaveBeenCalledWith("p","signed-preview",[1,2]));
  expect(screen.getByText("已处理 1 条 · 保存失败 1 条")).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"完成并关闭"}));
  expect(screen.getByRole("dialog",{name:"放弃未保存的批量登记"})).toBeVisible();
});

it("未保存编辑退出需明确放弃，继续编辑保留字段",()=>{
  const close=vi.fn();sheet([sample],{onClose:close});
  fireEvent.change(screen.getByRole("textbox",{name:"批量字段新值"}),{target:{value:"保留内容"}});
  fireEvent.keyDown(document,{key:"Escape"});
  expect(screen.getByRole("dialog",{name:"放弃未保存的批量登记"})).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"继续编辑"}));
  expect(screen.getByRole("textbox",{name:"批量字段新值"})).toHaveValue("保留内容");
  expect(close).not.toHaveBeenCalled();
});

it("跨页保留所选记录并使用全部精确身份打开批改",async()=>{
  vi.mocked(samples.listSamples).mockImplementation(async params=>({samples:params?.page===2?[{...sample,id:"r2",sample_id:"002"}]:[sample],pagination:{page:params?.page || 1,page_size:50,total:51,total_pages:2}}));
  const router=createMemoryRouter([{path:"*",element:<SampleRegistry/>}],{initialEntries:["/management/samples?project_id=p&asset_set=甲"]});
  render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("checkbox",{name:"选择登记 001（甲）"}));
  fireEvent.click(screen.getByRole("button",{name:"下一页"}));
  fireEvent.click(await screen.findByRole("checkbox",{name:"选择登记 002（甲）"}));
  expect(screen.getByText("已选择 2 条登记")).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"批量修改所选"}));
  expect(screen.getByRole("dialog",{name:"批量修改 2 条登记"})).toBeVisible();
  const inspect=vi.spyOn(batch,"previewSampleBatchRows").mockResolvedValue(preview(2));
  fireEvent.change(screen.getByRole("textbox",{name:"批量字段新值"}),{target:{value:"新值"}});
  fireEvent.click(screen.getByRole("button",{name:"预览登记变更"}));
  await waitFor(()=>expect(inspect.mock.calls[0][2].map(row=>row.record_id)).toEqual(["r1","r2"]));
});

it("不同数据集所选记录不能混合批改，手机仍能选择记录",async()=>{
  viewport.mobile=true;
  vi.mocked(samples.listSamples).mockResolvedValue({samples:[sample,{...sample,id:"r2",extra_metadata:{asset_set:"乙"}}]});
  render(<MemoryRouter><SampleRegistry/></MemoryRouter>);
  fireEvent.click(await screen.findByRole("checkbox",{name:"选择登记 001（甲）"}));
  fireEvent.click(screen.getByRole("checkbox",{name:"选择登记 001（乙）"}));
  expect(screen.getByRole("button",{name:"批量修改所选"})).toBeDisabled();
  expect(screen.getByText(/请先限定同一项目和数据集/)).toBeVisible();
});

it("模板准备失败保留范围并提供原位重试入口",async()=>{
  const download=vi.spyOn(batch,"downloadSampleBatchTemplate").mockRejectedValue(new Error("模板暂时无法下载"));
  sheet();fireEvent.click(screen.getByRole("button",{name:"下载所选登记模板"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("模板暂时无法下载");
  expect(download).toHaveBeenCalledWith("p","甲",["r1"]);
  expect(screen.getByRole("button",{name:"下载所选登记模板"})).toBeEnabled();
});

it("所选模板可在同一窗口上传，预览绑定原选择范围且确认前不保存", async () => {
  const inspect = vi.spyOn(batch, "previewSampleBatchFile").mockResolvedValue(preview());
  const save = vi.spyOn(batch, "applySampleBatch").mockResolvedValue({rows:[{row:1,sample_id:"001",status:"saved",message:"所选已保存"}],counts:{saved:1},asset_set:"甲"});
  sheet();
  fireEvent.click(screen.getByRole("radio", {name:/上传所选模板/}));
  expect(screen.queryByRole("checkbox", {name:"允许补充尚未关联输入的登记"})).toBeNull();
  const file = new File(["登记记录标识,原始样本编号,疾病\nr1,001,新值"], "所选登记.csv");
  fireEvent.change(screen.getByLabelText("上传批量登记表"), {target:{files:[file]}});
  fireEvent.click(screen.getByRole("button", {name:"预览登记变更"}));
  await screen.findByRole("button", {name:"确认保存 1 条"});
  expect(inspect).toHaveBeenCalledWith("p", "甲", file, false, ["r1"]);
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", {name:"确认保存 1 条"}));
  expect(await screen.findByText("所选已保存")).toBeVisible();
});

it("切换批量修改方式保留两种草稿，返回模板方式可直接预览", async () => {
  const inspect = vi.spyOn(batch, "previewSampleBatchFile").mockResolvedValue(preview());
  sheet();
  fireEvent.change(screen.getByRole("textbox", {name:"批量字段新值"}), {target:{value:"字段草稿"}});
  fireEvent.click(screen.getByRole("radio", {name:/上传所选模板/}));
  const file = new File(["data"], "保留模板.csv");
  fireEvent.change(screen.getByLabelText("上传批量登记表"), {target:{files:[file]}});
  fireEvent.click(screen.getByRole("radio", {name:/统一修改字段/}));
  expect(screen.getByRole("textbox", {name:"批量字段新值"})).toHaveValue("字段草稿");
  fireEvent.click(screen.getByRole("radio", {name:/上传所选模板/}));
  expect(screen.getByText("保留模板.csv")).toBeVisible();
  fireEvent.click(screen.getByRole("button", {name:"预览登记变更"}));
  await waitFor(() => expect(inspect).toHaveBeenCalledWith("p", "甲", file, false, ["r1"]));
});

it("手机可选择当前页全部记录并取消本页选择", async () => {
  viewport.mobile = true;
  vi.mocked(samples.listSamples).mockResolvedValue({samples:[sample,{...sample,id:"r2",sample_id:"002"}]});
  render(<MemoryRouter><SampleRegistry/></MemoryRouter>);
  fireEvent.click(await screen.findByRole("checkbox", {name:"选择当前页全部登记"}));
  expect(screen.getByText("已选择 2 条登记")).toBeVisible();
  expect(screen.getByRole("button", {name:"批量修改所选"})).toBeEnabled();
  fireEvent.click(screen.getByRole("checkbox", {name:"选择当前页全部登记"}));
  expect(screen.queryByText("已选择 2 条登记")).toBeNull();
});

it("文件预览客户端携带精确所选登记标识", async () => {
  const request = vi.fn().mockResolvedValue({ok:true,json:async () => preview()});
  vi.stubGlobal("fetch", request);
  const file = new File(["data"], "登记.csv");
  await batch.previewSampleBatchFile("p", "甲", file, false, ["r1", "r2"]);
  const body = request.mock.calls[0][1].body as FormData;
  expect(JSON.parse(String(body.get("record_ids")))).toEqual(["r1", "r2"]);
  expect(body.get("asset_set")).toBe("甲");
  expect(body.get("file")).toBe(file);
});
