import { useState } from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { GoKeggConfig } from "../features/scripthub/modules/GoKeggConfig";
import { apiClient } from "../shared/api/client";
vi.mock("../shared/api/client", () => ({apiClient:{get:vi.fn(),post:vi.fn()}}));
function Harness() {
  const [value, setValue] = useState<Record<string, unknown>>({input_mode:"deg"});
  return <><GoKeggConfig projectId="p" module="go-kegg-enrichment" groupSpecs={[]} loadingSpecs={false}
    sourceContext={{projectId:"p",assetSetId:"Set1",transcriptomePath:"/expression.csv",sampleNames:[],chains:[],profileFields:[],groupFields:[],pepColumns:[]}}
    value={value} onChange={setValue}/><output data-testid="config">{JSON.stringify(value)}</output></>;
}
describe("富集来源", () => {
 it("选择当前数据集结果，保留产物标识并隐藏无效的重算参数", async () => {
  vi.mocked(apiClient.get).mockResolvedValue({candidates:[
   {id:"source:deg",status:"available",created_at:"2026-09-16T08:00:00",metadata:{comparisons:[{group1:"甲",group2:"乙"}],pvalue_threshold:0.01,logfc_cutoff:2}},
   {id:"missing:deg",status:"unavailable",reason:"来源文件已删除",metadata:{}}
  ]});
  render(<Harness/>);
  await screen.findByRole("option",{name:/甲 与 乙/});
  expect(apiClient.get).toHaveBeenCalledWith("/api/script-hub/go-kegg-enrichment/sources",{project_id:"p",asset_set:"Set1"},{skipCache:true});
  expect(apiClient.post).not.toHaveBeenCalled();
  expect(screen.queryByText("表达差异比较")).toBeNull();
  expect(screen.getByRole("option",{name:/来源文件已删除/})).toBeDisabled();
  fireEvent.change(screen.getByLabelText("来源差异表达结果"),{target:{value:"source:deg"}});
  expect(JSON.parse(screen.getByTestId("config").textContent!).upstream_artifact_id).toBe("source:deg");
  expect(screen.getByText(/上游 p 值阈值：0.01/)).toBeInTheDocument();
  vi.mocked(apiClient.post).mockResolvedValue({success:true,groups:[],comparisons:[]});
  fireEvent.change(screen.getByLabelText("输入方式"),{target:{value:"expression"}});
  await waitFor(()=>expect(screen.getByText("表达差异比较")).toBeInTheDocument());
  expect(JSON.parse(screen.getByTestId("config").textContent!).upstream_artifact_id).toBeUndefined();
 });
});
