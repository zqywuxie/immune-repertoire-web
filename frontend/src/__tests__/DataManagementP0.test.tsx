import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useNavigate, useLocation } from "react-router-dom";
import { SampleRegistry } from "../pages/management/SampleRegistry";
import { AssetTable } from "../features/assets/AssetTable";
import * as samplesApi from "../shared/api/samples";
import { AssetUpload } from "../features/assets/AssetUpload";
import { ProjectDatasetManager } from "../features/assets/ProjectDatasetManager";
import { SampleEditSheet } from "../features/samples/SampleEditSheet";
import { GroupSpecSelect } from "../features/scripthub/modules/shared";
import { Stage3ModuleConfig } from "../features/scripthub/stages/Stage3ModuleConfig";
import * as projects from "../shared/api/projects";
import * as groups from "../shared/api/groupSpecs";
import { apiClient } from "../shared/api/client";
import type { SampleRecord } from "../shared/api/samples";

beforeEach(() => { vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[]}); });
afterEach(() => {cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();apiClient.invalidateCache();});
const sample = {id:"r",project_id:"p",project_name:"项目",sample_id:"001",sample_name:"原名称",institution:"甲机构",spices:"人",sequence_id:null,chain_flag:null,is_healthy:null,illness:null,is_pe:null,contain_method:null,iso_tag:null,created_at:null,updated_at:null,extra_metadata:{asset_set:"甲"}} as SampleRecord;
const source = {id:"a",project_id:"p",asset_type:"profile",original_name:"指标.csv",size:1,storage_path:"/synthetic/profile.csv",metadata:{asset_set:"甲"}} as projects.AssetListResponse["assets"][number];

it("只提交改变的登记字段，明确清空与未修改字段区分", async () => {
  const save=vi.fn().mockResolvedValue(undefined);
  render(<SampleEditSheet sample={sample} open onClose={vi.fn()} onSave={save}/>);
  fireEvent.change(screen.getByRole("textbox",{name:"样本名称"}),{target:{value:"新名称"}});
  fireEvent.change(screen.getByRole("textbox",{name:"所属机构"}),{target:{value:""}});
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  await waitFor(()=>expect(save).toHaveBeenCalledWith({sample_name:"新名称",institution:"",expected_values:{sample_name:"原名称",institution:"甲机构"}}));
});

it("上传模式切换先确认，继续编辑保留文件，放弃后才清空", async () => {
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[source]});
  const upload=vi.spyOn(projects,"uploadProjectAssets").mockResolvedValue({assets:[source]});
  render(<AssetUpload projectId="p" onSuccess={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText("上传样本指标表（逗号分隔、制表符分隔或表格文件）",{selector:"input"}),{target:{files:[new File(["sample,value\n001,1"],"草稿.csv")]}});
  fireEvent.click(screen.getByRole("button",{name:"导入到哪里"}));
  fireEvent.click(screen.getByRole("option",{name:"添加到已有数据集"}));
  expect(screen.getByRole("alert")).toHaveTextContent("放弃本次未保存");
  fireEvent.click(screen.getByRole("button",{name:"继续编辑"}));
  expect(screen.getByRole("button",{name:"从提交清单移除 草稿.csv"})).toBeInTheDocument();
  expect(upload).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"导入到哪里"}));
  fireEvent.click(screen.getByRole("option",{name:"添加到已有数据集"}));
  fireEvent.click(screen.getByRole("button",{name:"放弃本次选择并切换"}));
  expect(screen.queryByRole("region",{name:"本次提交清单"})).not.toBeInTheDocument();
});

function Nav() { const navigate=useNavigate();const location=useLocation();return <><button onClick={()=>navigate(-1)}>浏览器后退</button><button onClick={()=>navigate(1)}>浏览器前进</button><output aria-label="当前地址">{location.search}</output></>; }
it("上传面板收起与浏览器后退保留草稿，重新打开恢复原文件", async () => {
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[]});
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[]});
  render(<MemoryRouter initialEntries={["/?asset_set="]}><Nav/><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/></MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"导入文件"}));
  const input=await screen.findByLabelText("上传样本指标表（逗号分隔、制表符分隔或表格文件）",{selector:"input"});
  fireEvent.change(input,{target:{files:[new File(["sample,value\n001,1"],"保留.csv")]}});
  fireEvent.click(screen.getByRole("button",{name:"浏览器后退"}));
  await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByText("已保留 1 项未保存选择，可继续上传。")).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"浏览器前进"}));
  expect(await screen.findByRole("button",{name:"从提交清单移除 保留.csv"})).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"关闭"}));
  fireEvent.click(await screen.findByRole("button",{name:"继续编辑上传"}));
  expect(await screen.findByRole("button",{name:"从提交清单移除 保留.csv"})).toBeVisible();
});

it("不匹配方案显示来源与原因且不能选择", () => {
  render(<GroupSpecSelect value={{group_spec_id:"s"}} setField={vi.fn()} loadingSpecs={false} groupSpecs={[{id:"s",project_id:"p",name:"旧版本方案",spec_json:{groups:["A","B"]},source:{asset_id:"a",name:"旧指标.csv",asset_set:"甲",content_version:"version-a",available:false,reason:"方案来源版本与当前指标表不同。"}}]}/>);
  expect(screen.getByRole("option",{name:/旧版本方案 · 甲 · 旧指标.csv/})).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("请选择匹配方案");
});

it("配置阶段把不匹配来源传给继续运行的阻断状态", async () => {
  vi.spyOn(groups,"listGroupSpecs").mockResolvedValue({group_specs:[{id:"s",project_id:"p",name:"旧版本方案",source:{asset_id:"a",name:"指标.csv",asset_set:"甲",available:false,reason:"版本不同"}}]});
  const issue=vi.fn();
  render(<Stage3ModuleConfig fixedModule="profile" projectId="p" modules={[]} selectedModules={["profile"]} moduleConfigs={{profile:{group_spec_id:"s"}}} onUpdate={vi.fn()} onGroupSpecIssue={issue} sourceContext={{assetSetId:"甲",profilePath:"/synthetic/new.csv",sampleNames:[],chains:[],profileFields:[],groupFields:[],pepColumns:[]}}/>);
  await waitFor(()=>expect(issue).toHaveBeenLastCalledWith("旧版本方案：版本不同"));
  expect(groups.listGroupSpecs).toHaveBeenCalledWith("p",{assetSet:"甲",profilePath:"/synthetic/new.csv"});
});


it("全部数据集覆盖可定位缺口，未知校验包含在待处理数量", async () => {
  const assets=vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[]});
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[
    {name:"甲",input_count:1,kinds:{profile:{count:1,statuses:{unknown:1},sample_min:null,sample_max:null}}},
    {name:"乙",input_count:1,kinds:{transcriptome:{count:1,statuses:{valid:1},sample_min:null,sample_max:null}}},
  ]});
  render(<MemoryRouter initialEntries={["/?asset_set="]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/></MemoryRouter>);
  fireEvent.click(await screen.findByText("各数据集输入覆盖 · 2 个数据集"));
  expect(await screen.findByRole("button",{name:"查看 甲 的转录组：未提供"})).toBeVisible();
  expect(screen.getByRole("button",{name:"处理 1 项"})).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"查看 甲 的样本指标表：1 项需处理"}));
  await waitFor(()=>expect(assets).toHaveBeenLastCalledWith("p",expect.objectContaining({assetSet:"甲",assetType:"profile",validationStatus:"needs_attention"})));
});

it("已打开文件详情跟随校验终态，等待结束后可重新校验", async () => {
  vi.spyOn(apiClient,"get").mockResolvedValue({columns:[],rows:[],directory:false,files:[],pagination:{page:1,page_size:20,total:0,total_pages:0}});
  const {rerender}=render(<AssetTable projectId="p" assets={[{...source,metadata:{asset_set:"甲",validation:{status:"pending"}}}]} loading={false}/>);
  fireEvent.click(screen.getByRole("button",{name:"查看 指标.csv"}));
  const dialog=screen.getByRole("dialog",{name:"文件详情与校验"});
  expect(within(dialog).getByRole("button",{name:"重新校验"})).toBeDisabled();
  rerender(<AssetTable projectId="p" assets={[{...source,metadata:{asset_set:"甲",validation:{status:"valid"}}}]} loading={false}/>);
  await waitFor(()=>expect(within(dialog).getByRole("button",{name:"重新校验"})).toBeEnabled());
  expect(within(dialog).getByText("校验通过")).toBeVisible();
});

it("登记表中文展示历史值，高级条件收起后仍可识别和移除", async () => {
  vi.spyOn(samplesApi,"listSamples").mockResolvedValue({samples:[{...sample,spices:"human",is_healthy:"yes",is_pe:"no"}],pagination:{page:1,page_size:50,total:1,total_pages:1}});
  vi.spyOn(samplesApi,"getSampleFieldOptions").mockResolvedValue({fields:{spices:["人","human","斑马鱼"]}});
  render(<MemoryRouter initialEntries={["/?project_id=p&asset_set=甲&institution=甲机构"]}><SampleRegistry/></MemoryRouter>);
  const row=await screen.findByRole("row",{name:/001 原名称/});
  expect(within(row).getByText("健康")).toBeVisible();
  expect(within(row).getByText("人")).toBeVisible();
  expect(within(row).getByText("否")).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:/高级筛选/}));
  expect(screen.getByRole("button",{name:"移除机构筛选：甲机构"})).toBeVisible();
  fireEvent.click(screen.getByText("物种 · 全部物种"));
  expect(screen.getByRole("group",{name:"物种多选"})).toHaveTextContent("斑马鱼");
  expect(screen.getAllByRole("group",{name:"物种多选"})).toHaveLength(1);
  fireEvent.click(screen.getByRole("button",{name:"移除机构筛选：甲机构"}));
  await waitFor(()=>expect(samplesApi.listSamples).toHaveBeenLastCalledWith(expect.objectContaining({project_id:"p",asset_set:"甲"})));
});
