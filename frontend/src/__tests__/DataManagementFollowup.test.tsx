import { Sheet } from "../shared/components/Sheet";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, RouterProvider, createMemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { UnsavedChangesGuard } from "../shared/components/UnsavedChangesGuard";
import { AssetUpload } from "../features/assets/AssetUpload";
import { ProjectDatasetManager } from "../features/assets/ProjectDatasetManager";
import { ProjectGroupSpecs } from "../features/projects/ProjectGroupSpecs";
import { SampleRegistry } from "../pages/management/SampleRegistry";
import { Stage3ModuleConfig } from "../features/scripthub/stages/Stage3ModuleConfig";
import * as projects from "../shared/api/projects";
import * as samples from "../shared/api/samples";
import * as groups from "../shared/api/groupSpecs";
import { apiClient } from "../shared/api/client";

beforeEach(() => { vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[]}); });
afterEach(() => { cleanup();vi.restoreAllMocks();apiClient.invalidateCache(); });
const source={id:"a",project_id:"p",asset_type:"profile",original_name:"指标.csv",storage_path:"/synthetic/a.csv",size:2,metadata:{asset_set:"甲"}};
const datasets={datasets:["甲","乙"].map(name=>({name,input_count:1,kinds:{profile:{count:1,statuses:{valid:1},sample_min:1,sample_max:1}}}))};

function GuardPage({ group=false }: { group?: boolean }) {
  const navigate=useNavigate();const location=useLocation();
  return <><UnsavedChangesGuard when queryKeys={group ? ["tab","asset_set"] : []}/><output aria-label="地址">{location.pathname+location.search}</output>
    <input aria-label="编辑内容" defaultValue="未保存内容"/><button onClick={()=>navigate("/analysis/center")}>去分析</button>
    <button onClick={()=>navigate("?tab=samples")}>切换页签</button><button onClick={()=>navigate(-1)}>返回上一页</button></>;
}
it("路由离开和后退可取消，项目内上传页签切换保留草稿",async()=>{
  const router=createMemoryRouter([{path:"*",element:<GuardPage/>}],{initialEntries:["/management/projects","/management/projects/p?tab=assets"],initialIndex:1});
  render(<RouterProvider router={router}/>);
  fireEvent.change(screen.getByLabelText("编辑内容"),{target:{value:"保留草稿"}});
  fireEvent.click(screen.getByRole("button",{name:"返回上一页"}));
  expect(await screen.findByRole("dialog",{name:"离开前确认未保存内容"})).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"继续编辑"}));
  expect(screen.getByLabelText("编辑内容")).toHaveValue("保留草稿");
  expect(screen.getByLabelText("地址")).toHaveTextContent("/management/projects/p?tab=assets");
  fireEvent.click(screen.getByRole("button",{name:"切换页签"}));
  await waitFor(()=>expect(screen.getByLabelText("地址")).toHaveTextContent("tab=samples"));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"去分析"}));
  fireEvent.click(await screen.findByRole("button",{name:"放弃并离开"}));
  await waitFor(()=>expect(router.state.location.pathname).toBe("/analysis/center"));
});
it("分组未保存时项目内页签切换也先确认",async()=>{
  const router=createMemoryRouter([{path:"*",element:<GuardPage group/>}],{initialEntries:["/management/projects/p?tab=group-specs"]});
  render(<RouterProvider router={router}/>);
  fireEvent.click(screen.getByRole("button",{name:"切换页签"}));
  fireEvent.click(await screen.findByRole("button",{name:"继续编辑"}));
  expect(router.state.location.search).toBe("?tab=group-specs");
});
it("移除待上传卡片只删除本卡片草稿，取消移除保持所有草稿",async()=>{
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[]});
  render(<AssetUpload projectId="p" onSuccess={vi.fn()}/>);
  fireEvent.click(screen.getByRole("button",{name:"添加数据集"}));
  document.querySelectorAll("details").forEach(node=>node.setAttribute("open",""));
  const paths=screen.getAllByPlaceholderText("/data/projects/.../pep_sample_dir/");
  fireEvent.change(paths[0],{target:{value:"/synthetic/keep"}});
  fireEvent.change(paths[1],{target:{value:"/synthetic/remove"}});
  fireEvent.click(screen.getAllByTitle("移除数据集")[1]);
  fireEvent.click(screen.getByRole("button",{name:"继续编辑"}));
  expect(paths[1]).toHaveValue("/synthetic/remove");
  fireEvent.click(screen.getAllByTitle("移除数据集")[1]);
  fireEvent.click(screen.getByRole("button",{name:"放弃选择并移除数据集"}));
  expect(screen.getAllByPlaceholderText("/data/projects/.../pep_sample_dir/")).toHaveLength(1);
  expect(screen.getByPlaceholderText("/data/projects/.../pep_sample_dir/")).toHaveValue("/synthetic/keep");
});
it("上传内部切换数据集后标题和校验查询同步",async()=>{
  const list=vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[source,{...source,id:"b",metadata:{asset_set:"乙"}}]});
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue(datasets);
  render(<MemoryRouter initialEntries={["/?asset_set=甲"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/></MemoryRouter>);
  await screen.findByText("甲 · 1 个输入文件");
  fireEvent.click(screen.getByRole("button",{name:"导入文件"}));
  const dialog=await screen.findByRole("dialog",{name:"导入数据：甲"});
  fireEvent.click(within(dialog).getByRole("button",{name:"已有数据集"}));
  fireEvent.click(screen.getByRole("option",{name:"乙 · 1 个文件"}));
  const updatedDialog=await screen.findByRole("dialog",{name:"导入数据：乙"});
  const validation=await within(updatedDialog).findByText("乙 · 1 个输入文件 · 查看校验状态");
  fireEvent.click(validation);
  await waitFor(()=>expect(list).toHaveBeenCalledWith("p",expect.objectContaining({assetSet:"乙",pageSize:20,skipCache:true})));
});
it("分组切换编辑先确认，继续编辑保留当前改动",async()=>{
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[]});
  render(<MemoryRouter><ProjectGroupSpecs projectId="p" loading={false} onChanged={vi.fn()} groupSpecs={[{id:"s",name:"旧方案",spec_json:{groups:["甲","乙"]}}]}/></MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"编辑"}));
  fireEvent.change(screen.getByRole("textbox",{name:"方案名称"}),{target:{value:"未保存改名"}});
  fireEvent.click(screen.getByRole("button",{name:"新建分组方案"}));
  fireEvent.click(await screen.findByRole("button",{name:"继续编辑"}));
  expect(screen.getByRole("textbox",{name:"方案名称"})).toHaveValue("未保存改名");
  fireEvent.click(screen.getByRole("button",{name:"新建分组方案"}));
  fireEvent.click(screen.getByRole("button",{name:"放弃修改并继续"}));
  expect(screen.getByRole("textbox",{name:"方案名称"})).toHaveValue("");
});
it("分组读取失败后原地重试并恢复继续运行条件",async()=>{
  const list=vi.spyOn(groups,"listGroupSpecs").mockRejectedValueOnce(new Error("暂时不可用")).mockResolvedValue({group_specs:[{id:"s",project_id:"p",name:"方案"}]});
  const issue=vi.fn();
  render(<Stage3ModuleConfig fixedModule="profile" projectId="p" modules={[]} selectedModules={["profile"]} moduleConfigs={{profile:{group_spec_id:"s"}}} onUpdate={vi.fn()} onGroupSpecIssue={issue}/>);
  fireEvent.click(await screen.findByRole("button",{name:"重新读取分组方案"}));
  await waitFor(()=>expect(issue).toHaveBeenLastCalledWith(""));
  expect(list).toHaveBeenCalledTimes(2);
});
it("零结果保留项目范围，多物种逐项选择与取消且不跨范围",async()=>{
  const list=vi.spyOn(samples,"listSamples").mockResolvedValue({samples:[],pagination:{page:1,page_size:50,total:0,total_pages:0}});
  vi.spyOn(samples,"getSampleFieldOptions").mockResolvedValue({fields:{spices:["人","mouse","斑马鱼"]}});
  vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"研究项目"} as never);
  render(<MemoryRouter initialEntries={["/?project_id=p&asset_set=甲&spices=人,mouse"]}><SampleRegistry/></MemoryRouter>);
  expect(await screen.findByText("当前项目：研究项目 · 数据集：甲")).toBeVisible();
  expect(screen.queryByRole("combobox",{name:"项目"})).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("物种 · 人、小鼠"));
  expect(screen.getByRole("checkbox",{name:"人"})).toBeChecked();
  expect(screen.getByRole("checkbox",{name:"小鼠"})).toBeChecked();
  fireEvent.click(screen.getByRole("checkbox",{name:"小鼠"}));
  await waitFor(()=>expect(list).toHaveBeenLastCalledWith(expect.objectContaining({project_id:"p",asset_set:"甲",spices:"human"})));
  fireEvent.click(screen.getByRole("checkbox",{name:"斑马鱼"}));
  await waitFor(()=>expect(list).toHaveBeenLastCalledWith(expect.objectContaining({spices:"human,斑马鱼"})));
});

it("新建和已有数据集上传均只读取摘要，更新预检仅针对待提交范围",async()=>{
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue(datasets);
  const list=vi.spyOn(projects,"listProjectAssets");
  const impact=vi.spyOn(projects,"previewUploadImpact").mockImplementation(async(_id,items)=>({impacts:items.map(item=>({...item,assets:[],expected_versions:[],pagination:{page:1,page_size:20,total:0,total_pages:0}}))}));
  render(<AssetUpload projectId="p" onSuccess={vi.fn()}/>);
  await waitFor(()=>expect(projects.listProjectDatasets).toHaveBeenCalledWith("p"));
  expect(list).not.toHaveBeenCalled();expect(impact).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"导入到哪里"}));
  fireEvent.click(screen.getByRole("option",{name:"添加到已有数据集"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"已有数据集"})).toHaveTextContent("甲"));
  fireEvent.click(screen.getByRole("button",{name:"已有数据集"}));
  fireEvent.click(screen.getByRole("option",{name:"乙 · 1 个文件"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"已有数据集"})).toHaveTextContent("乙"));
  expect(list).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("选择新的样本指标表",{selector:"input"}),{target:{files:[new File(["sample,value\n001,1"],"乙新版.csv")]}});
  fireEvent.click(screen.getByRole("switch",{name:/更新当前版本/}));
  await waitFor(()=>expect(impact).toHaveBeenCalledWith("p",[{asset_set:"乙",asset_type:"profile",name:"乙新版.csv",directory:false}]));
  expect(list).not.toHaveBeenCalled();
});
it("新建数据集部分保存后失败项重试保持原数据集，不被新默认名覆盖",async()=>{
  let saved=false, fail=true;
  vi.spyOn(projects,"listProjectDatasets").mockImplementation(async()=>({datasets:saved ? [{name:"Set1",input_count:1,kinds:{}}] : []}));
  const upload=vi.spyOn(projects,"uploadProjectAssets").mockImplementation(async(_id,options)=>{
    if(options.assetType === "transcriptome" && fail) throw new Error("表达暂时失败");
    saved=true;return {assets:[{...source,metadata:{asset_set:options.assetSet}}]};
  });
  render(<AssetUpload projectId="p" onSuccess={vi.fn()}/>);
  await waitFor(()=>expect(projects.listProjectDatasets).toHaveBeenCalled());
  fireEvent.change(screen.getByLabelText("上传样本指标表（逗号分隔、制表符分隔或表格文件）",{selector:"input"}),{target:{files:[new File(["sample,value\n001,1"],"指标.csv")]}});
  fireEvent.change(screen.getByLabelText("将表达矩阵拖到此处（可选）",{selector:"input"}),{target:{files:[new File(["gene,001\nTP53,1"],"表达.csv")]}});
  fireEvent.click(screen.getByRole("button",{name:/保存数据/}));
  await screen.findByText(/已保存 1 个文件/);
  await waitFor(()=>expect(projects.listProjectDatasets).toHaveBeenCalledTimes(2));
  expect(screen.getByPlaceholderText("数据集名称")).toHaveValue("Set1");
  fail=false;fireEvent.click(screen.getByRole("button",{name:/保存数据/}));
  await waitFor(()=>expect(upload).toHaveBeenCalledTimes(3));
  expect(upload.mock.calls[2][1]).toMatchObject({assetType:"transcriptome",assetSet:"Set1"});
});

it("离开确认在已打开上传窗口之上，键盘只操作最上层窗口",()=>{
  const closeUpload=vi.fn(),closeConfirm=vi.fn();
  render(<><Sheet open onClose={closeUpload} title="上传"><button>上传动作</button></Sheet>
    <Sheet open layer={300} onClose={closeConfirm} title="确认"><button>确认动作</button></Sheet></>);
  fireEvent.keyDown(document,{key:"Escape"});
  expect(closeConfirm).toHaveBeenCalledTimes(1);
  expect(closeUpload).not.toHaveBeenCalled();
  const top=screen.getByRole("dialog",{name:"确认"});
  expect(Number(top.style.zIndex)).toBeGreaterThan(Number(screen.getByRole("dialog",{name:"上传"}).style.zIndex));
});
