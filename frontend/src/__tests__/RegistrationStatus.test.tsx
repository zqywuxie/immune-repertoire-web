import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import {ProjectInputSamples} from "../features/assets/ProjectInputSamples";
import {apiClient} from "../shared/api/client";

afterEach(()=>{cleanup();vi.restoreAllMocks();apiClient.invalidateCache();});
it("同名样本按数据集展示登记状态，已有登记打开当前范围，重复登记转到核对页",async()=>{
  const get=vi.spyOn(apiClient,"get").mockImplementation(async(url,params)=>{
    if(url.endsWith("/input-samples")) return {samples:[
      {sample_id:"001",asset_set:"甲",coverage:{},needs_version_selection:false,registration:{status:"registered",count:1}},
      {sample_id:"001",asset_set:"乙",coverage:{},needs_version_selection:false,registration:{status:"unregistered",count:0}},
      {sample_id:"002",asset_set:"甲",coverage:{},needs_version_selection:false,registration:{status:"multiple",count:2}},
    ],unresolved:[],note:"输入覆盖",pagination:{page:1,page_size:50,total:3,total_pages:1}} as never;
    if(url.endsWith("/registration")) return {sample:null,project_name:"研究项目"} as never;
    return {fields:{}} as never;
  });
  render(<MemoryRouter><ProjectInputSamples projectId="p" revision={0}/></MemoryRouter>);
  await screen.findByText("已登记");
  expect(screen.getByText("未登记")).toBeVisible();
  expect(screen.getByText("多条登记待核对")).toBeVisible();
  expect(screen.getByRole("link",{name:"核对登记"})).toHaveAttribute("href","/management/samples?project_id=p&asset_set=%E7%94%B2&input_sample_id=002");
  fireEvent.click(screen.getByRole("button",{name:"查看或编辑样本 001 的登记信息"}));
  await waitFor(()=>expect(get).toHaveBeenCalledWith("/api/projects/p/samples/registration",{sample_id:"001",asset_set:"甲"},{skipCache:true}));
});
