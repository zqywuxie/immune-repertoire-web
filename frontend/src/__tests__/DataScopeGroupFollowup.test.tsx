import {useState} from "react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {MemoryRouter,useLocation} from "react-router-dom";
import {ProjectDatasetManager} from "../features/assets/ProjectDatasetManager";
import {AssetTable} from "../features/assets/AssetTable";
import {AssetUpload} from "../features/assets/AssetUpload";
import {ProjectGroupSpecs} from "../features/projects/ProjectGroupSpecs";
import {GroupValueEditor} from "../features/projects/GroupValueEditor";
import {ApiError,apiClient} from "../shared/api/client";
import * as projects from "../shared/api/projects";
const asset={id:"a",project_id:"p",asset_type:"profile",original_name:"甲指标.csv",storage_path:"/synthetic/a.csv",metadata:{asset_set:"甲",content_version:"v-a"}};
const datasets={datasets:["甲","乙"].map(name=>({name,input_count:1,kinds:{profile:{count:1,statuses:{valid:1},sample_min:1,sample_max:1}}}))};
function Address(){return <output aria-label="当前地址">{useLocation().search}</output>;}
afterEach(()=>{cleanup();vi.restoreAllMocks();});
beforeEach(()=>{
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue(datasets);
 vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[],pagination:{page:1,page_size:50,total:0,total_pages:0}});
 vi.spyOn(projects,"getProjectAsset").mockResolvedValue({asset} as never);
 vi.spyOn(apiClient,"get").mockResolvedValue({items:[],pagination:{page:1,total_pages:1,total:0},columns:[],rows:[]});
});
it("数据集选择清除旧文件和方案详情，并保留搜索",async()=>{
 render(<MemoryRouter initialEntries={["/?asset_set=甲&asset=a&group_spec=s&file_q=指标"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/><Address/></MemoryRouter>);
 await screen.findByText("甲指标.csv");fireEvent.click(screen.getByRole("button",{name:"当前项目数据集"}));
 fireEvent.click(await screen.findByRole("option",{name:/乙 · 1/}));
 await waitFor(()=>expect(screen.getByLabelText("当前地址")).toHaveTextContent("asset_set=%E4%B9%99"));
 expect(screen.getByLabelText("当前地址").textContent).not.toMatch(/asset=|group_spec=/);expect(screen.getByLabelText("当前地址")).toHaveTextContent("file_q=");
 expect(screen.queryByRole("dialog",{name:"文件详情与校验"})).not.toBeInTheDocument();
});
it("跨范围深链提示所属数据集，不把旧文件当成当前范围文件",async()=>{
 render(<MemoryRouter><AssetTable projectId="p" assetSet="乙" assets={[]} focusedAssetId="a" loading={false}/></MemoryRouter>);
 await screen.findByText("此文件属于其他数据集");
 expect(screen.getByRole("link",{name:"切换到所属数据集查看"})).toHaveAttribute("href",expect.stringContaining("asset_set=%E7%94%B2"));
 expect(screen.queryByRole("link",{name:"检查映射与开始分析"})).not.toBeInTheDocument();
});
it("摘要读取失败时，新建导入保留文件且不能隐式使用默认名称保存",async()=>{
 vi.mocked(projects.listProjectDatasets).mockRejectedValue(new Error("摘要断连"));
 render(<AssetUpload projectId="p" initialAssetType="profile" onSuccess={vi.fn()}/>);
 await screen.findByText(/数据集摘要读取失败/);
 fireEvent.change(screen.getByLabelText("上传样本指标表（逗号分隔、制表符分隔或表格文件）",{selector:"input"}),{target:{files:[new File(["sample,value\n001,1"],"指标.csv")]}});
 expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeDisabled();expect(screen.getAllByText("指标.csv").length).toBeGreaterThan(0);
});
it("新建导入的同名范围必须显式确认，确认不打开更新开关",async()=>{
 render(<AssetUpload projectId="p" initialAssetType="profile" onSuccess={vi.fn()}/>);
 await waitFor(()=>expect(projects.listProjectDatasets).toHaveBeenCalled());
 fireEvent.change(screen.getByLabelText("数据集 1 名称"),{target:{value:"甲"}});
 fireEvent.change(screen.getByLabelText("上传样本指标表（逗号分隔、制表符分隔或表格文件）",{selector:"input"}),{target:{files:[new File(["sample,value\n001,1"],"指标.csv")]}});
 expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeDisabled();
 fireEvent.click(screen.getByRole("checkbox",{name:"确认使用这些已有数据集"}));expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeEnabled();
});
it("方案保存冲突保留完整对象分组，另存使用新名称且不带旧版本令牌",async()=>{
 const scheme={id:"s",revision:"read-version",name:"原方案",spec_json:{groups:[{name:"甲",color:"red"},{name:"乙",color:"blue"}],description:"原属性"}};
 const post=vi.spyOn(apiClient,"post").mockRejectedValueOnce(new ApiError("方案冲突",409,{error_code:"GROUP_SPEC_CHANGED"})).mockResolvedValue({});
 render(<MemoryRouter><ProjectGroupSpecs projectId="p" loading={false} groupSpecs={[scheme]} onChanged={vi.fn()}/></MemoryRouter>);
 fireEvent.click(screen.getByRole("button",{name:"编辑"}));fireEvent.change(screen.getByRole("textbox",{name:"分组名称（按顺序，用逗号或顿号分隔）"}),{target:{value:"乙、甲"}});
 fireEvent.click(screen.getByRole("button",{name:"保存"}));await screen.findByText("方案已在其他页面更新");
 expect(post.mock.calls[0][1]).toMatchObject({id:"s",expected_revision:"read-version"});expect(screen.getByRole("button",{name:"保存"})).toBeDisabled();
 fireEvent.click(screen.getByRole("button",{name:"另存当前编辑"}));fireEvent.click(screen.getByRole("button",{name:"保存"}));
 await waitFor(()=>expect(post).toHaveBeenCalledTimes(2));expect(post.mock.calls[1][1]).toEqual({name:"原方案（副本）",spec_json:{description:"原属性",groups:[scheme.spec_json.groups[1],scheme.spec_json.groups[0]]}});
});
it("右侧筛选隐藏新增分组时提供定位，并保留其他成员",()=>{
 function Harness(){const [order,setOrder]=useState(["甲"]);return <GroupValueEditor values={["甲","乙"]} order={order} onChange={setOrder} countLabel={()=>"1 个样本编号"} disabled={false}/>;}
 render(<Harness/>);fireEvent.change(screen.getByRole("textbox",{name:"搜索已选分组"}),{target:{value:"甲"}});fireEvent.click(screen.getByRole("checkbox",{name:/乙/}));
 expect(screen.getByText(/已加入「乙」/)).toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:"定位新增分组"}));expect(screen.getByRole("textbox",{name:"搜索已选分组"})).toHaveValue("");
 expect(screen.getByText("1. 甲")).toBeInTheDocument();expect(screen.getByText("2. 乙")).toBeInTheDocument();
});
