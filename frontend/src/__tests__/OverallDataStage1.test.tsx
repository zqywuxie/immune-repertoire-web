import {afterEach, expect, it, vi} from "vitest";
import {cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {MemoryRouter, useLocation} from "react-router-dom";
import {SampleEditSheet} from "../features/samples/SampleEditSheet";
import {ProjectInputSamples} from "../features/assets/ProjectInputSamples";
import {ApiError, apiClient} from "../shared/api/client";
import type {SampleRecord} from "../shared/api/samples";

afterEach(() => {cleanup(); vi.restoreAllMocks(); apiClient.invalidateCache();});

const original: SampleRecord = {id:"r", project_id:"p", project_name:"研究项目", sample_id:"001",
  sample_name:"样本001", sequence_id:null, spices:null, institution:"原机构", chain_flag:null,
  is_healthy:null, illness:null, is_pe:null, contain_method:null, iso_tag:null,
  extra_metadata:{asset_set:"甲"}, created_at:null, updated_at:null};

it("同字段冲突保留草稿，核对后采用其他字段最新值且只保存本次修改", async () => {
  vi.spyOn(apiClient,"get").mockResolvedValue({fields:{}});
  const latest = {...original, institution:"他人机构", illness:"他人新增疾病"};
  const save = vi.fn().mockRejectedValueOnce(new ApiError("登记已更新，草稿已保留",409,{
    error_code:"SAMPLE_RECORD_CHANGED", details:{sample:latest, conflicts:{institution:{expected:"原机构",current:"他人机构",submitted:"我的机构"}}},
  })).mockResolvedValue(undefined);
  const close = vi.fn();
  render(<MemoryRouter><SampleEditSheet sample={original} open onSave={save} onClose={close}/></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("所属机构"),{target:{value:"我的机构"}});
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  await screen.findByRole("region",{name:"核对登记变化"});
  expect(save).toHaveBeenNthCalledWith(1,{institution:"我的机构",expected_values:{institution:"原机构"}});
  expect(screen.getByLabelText("所属机构")).toHaveValue("我的机构");
  expect(screen.getByRole("button",{name:"保存"})).toBeDisabled();
  expect(close).not.toHaveBeenCalled();
  expect(screen.getByText("最新值：他人机构")).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"保留修改，更新对照"}));
  expect(screen.getByLabelText("疾病")).toHaveValue("他人新增疾病");
  expect(screen.getByLabelText("所属机构")).toHaveValue("我的机构");
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  await waitFor(()=>expect(close).toHaveBeenCalledOnce());
  expect(save).toHaveBeenNthCalledWith(2,{institution:"我的机构",expected_values:{institution:"他人机构"}});
});

function Address() {return <output aria-label="当前地址">{useLocation().search}</output>;}

it("登记筛选与输入状态独立，重置页码并在清除时保留项目数据集",async()=>{
  const get = vi.spyOn(apiClient,"get").mockImplementation(async (url,params) => {
    if (url.endsWith("/input-samples")) return {samples:[],unresolved:[],note:"输入覆盖",pagination:{page:params?.page,page_size:50,total:500,total_pages:10}} as never;
    return {fields:{}} as never;
  });
  render(<MemoryRouter initialEntries={["/management/projects/p?asset_set=%E7%94%B2&sample_page=3&sample_state=multiple"]}>
    <ProjectInputSamples projectId="p" revision={0}/><Address/>
  </MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"样本登记状态筛选"}));
  fireEvent.click(screen.getByRole("option",{name:"未登记"}));
  await waitFor(()=>expect(get).toHaveBeenCalledWith("/api/projects/p/input-samples",expect.objectContaining({
    asset_set:"甲",state:"multiple",registration_state:"unregistered",page:1,page_size:50,
  })));
  expect(screen.getByLabelText("当前地址").textContent).toContain("sample_registration=unregistered");
  expect(screen.getByLabelText("当前地址").textContent).not.toContain("sample_page");
  fireEvent.click(screen.getByRole("button",{name:"清除样本筛选"}));
  await waitFor(()=>expect(get).toHaveBeenLastCalledWith("/api/projects/p/input-samples",expect.objectContaining({
    asset_set:"甲",state:"",registration_state:"",page:1,
  })));
  expect(screen.getByLabelText("当前地址").textContent).toBe("?asset_set=%E7%94%B2");
});
