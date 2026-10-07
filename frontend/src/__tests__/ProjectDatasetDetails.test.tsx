import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {ProjectDatasetDetails} from "../features/assets/ProjectDatasetDetails";
import {ProjectDatasetManager} from "../features/assets/ProjectDatasetManager";
import * as projects from "../shared/api/projects";
import {ApiError} from "../shared/api/client";
import {MemoryRouter} from "react-router-dom";
const dataset={name:"甲",input_count:1,kinds:{},display_name:"原名称",revision:1,source:"原来源"};
afterEach(()=>{cleanup();vi.restoreAllMocks();});

it("数据集保存失败保留说明草稿，取消先确认，成功仅传变更且保留关联标识",async()=>{
 const save=vi.spyOn(projects,"updateProjectDataset").mockRejectedValueOnce(new Error("保存中断"))
 .mockResolvedValueOnce({dataset:{...dataset,display_name:"新名称",archived:true,revision:2}});
 const dirty=vi.fn(),changed=vi.fn();render(<ProjectDatasetDetails projectId="p" dataset={dataset} onChange={changed} onDirty={dirty}/>);
 fireEvent.click(screen.getByRole("button",{name:"编辑数据集说明"}));
 fireEvent.change(screen.getByRole("textbox",{name:"显示名称（必填）"}),{target:{value:"新名称"}});
 fireEvent.click(screen.getByRole("checkbox",{name:"归档此数据集"}));
 fireEvent.click(screen.getByRole("button",{name:"取消"}));expect(screen.getByRole("dialog",{name:"放弃未保存的数据集说明？"})).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"继续编辑"}));
 fireEvent.click(screen.getByRole("button",{name:"保存说明"}));expect(await screen.findByRole("alert")).toHaveTextContent("保存中断");
 expect(screen.getByRole("textbox",{name:"显示名称（必填）"})).toHaveValue("新名称");
 fireEvent.click(screen.getByRole("button",{name:"保存说明"}));
 await waitFor(()=>expect(changed).toHaveBeenCalledOnce());
 expect(save).toHaveBeenLastCalledWith("p",{asset_set:"甲",expected_revision:1,display_name:"新名称",archived:true});
 expect(dirty).toHaveBeenCalledWith(false);
});

it("说明并发冲突核对后保留改名草稿，采用他人更新的来源而不覆写",async()=>{
 const latest={...dataset,display_name:"他人名称",source:"最新来源",revision:2};
 const save=vi.spyOn(projects,"updateProjectDataset").mockRejectedValueOnce(new ApiError("说明已更新",409,{details:{dataset:latest}}))
 .mockResolvedValueOnce({dataset:{...latest,display_name:"本次名称",revision:3}});
 render(<ProjectDatasetDetails projectId="p" dataset={dataset} onChange={vi.fn()}/>);
 fireEvent.click(screen.getByRole("button",{name:"编辑数据集说明"}));fireEvent.change(screen.getByRole("textbox",{name:"显示名称（必填）"}),{target:{value:"本次名称"}});
 fireEvent.click(screen.getByRole("button",{name:"保存说明"}));await screen.findByRole("region",{name:"核对数据集说明变化"});
 expect(screen.getByRole("button",{name:"保存说明"})).toBeDisabled();fireEvent.click(screen.getByRole("button",{name:"保留修改，更新对照"}));
 expect(screen.getByRole("textbox",{name:"数据来源"})).toHaveValue("最新来源");
 fireEvent.click(screen.getByRole("button",{name:"保存说明"}));await waitFor(()=>expect(save).toHaveBeenCalledTimes(2));
 expect(save).toHaveBeenLastCalledWith("p",{asset_set:"甲",expected_revision:2,display_name:"本次名称"});
});

it("归档数据集可显式显示并编辑恢复，显示名变更仍以原范围读取输入",async()=>{
 const list=vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[]});
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[{...dataset,archived:true}]});
 render(<MemoryRouter initialEntries={["/?asset_set="]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/></MemoryRouter>);
 const check=await screen.findByRole("checkbox",{name:"显示已归档数据集"});fireEvent.click(check);
 fireEvent.click(screen.getByRole("button",{name:"当前项目数据集"}));fireEvent.click(screen.getByRole("option",{name:"原名称 · 已归档 · 1 个输入文件"}));
 await screen.findByRole("button",{name:"编辑数据集说明"});
 expect(list).toHaveBeenLastCalledWith("p",expect.objectContaining({assetSet:"甲"}));
 expect(screen.getByText(/此数据集已从默认候选列表收起/)).toBeVisible();
});
