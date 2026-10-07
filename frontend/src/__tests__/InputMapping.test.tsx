import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { InputMappingPanel } from "../features/scripthub/InputMappingPanel";
import * as projects from "../shared/api/projects";
import { apiClient } from "../shared/api/client";
afterEach(() => {cleanup(); vi.restoreAllMocks();});
function openMapping() {
  fireEvent.click(screen.getByText("工作表、编号列与样本编号对应"));
}
it("限定数据集，选择工作表和编号列后保存并重新检查", async () => {
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets: [
    {id:"one",asset_type:"profile",original_name:"样本.xlsx",metadata:{asset_set:"Set2"}},
    {id:"other",asset_type:"profile",original_name:"其他.csv",metadata:{asset_set:"Set1"}},
  ]} as unknown as Awaited<ReturnType<typeof projects.listProjectAssets>>);
  const post=vi.spyOn(apiClient,"post").mockResolvedValueOnce({sheets:["说明","数据"],selected_sheet:"说明",columns:["说明"],preview_rows:[],requires_sheet_selection:true})
    .mockResolvedValueOnce({sheets:["说明","数据"],selected_sheet:"数据",columns:["编号","分组"],preview_rows:[["0001","甲"]]})
    .mockResolvedValueOnce({success:true});
  const saved=vi.fn();
  render(<InputMappingPanel projectId="p" assetSet="Set2" onSaved={saved}/>);
  openMapping();
  await screen.findByRole("option",{name:"样本.xlsx"});
  expect(screen.queryByRole("option",{name:"其他.csv"})).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("原始数据文件"),{target:{value:"one"}});
  await screen.findByLabelText("数据工作表");
  expect(screen.getAllByRole("combobox")[1]).toHaveValue("");
  fireEvent.change(screen.getByLabelText("数据工作表"),{target:{value:"数据"}});
  await screen.findByText("0001");
  fireEvent.change(screen.getByLabelText("样本编号列"),{target:{value:"编号"}});
  fireEvent.click(screen.getByRole("button",{name:"保存映射并重新检查"}));
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenLastCalledWith("/api/projects/p/assets/one/prepare-input",{identifier_column:"编号",sheet_name:"数据"});
  const reset=vi.spyOn(apiClient,"delete").mockResolvedValue({success:true,changed:true});
  fireEvent.click(screen.getByRole("button",{name:"恢复使用原始文件"}));
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(2));
  expect(reset).toHaveBeenCalledWith("/api/projects/p/assets/one/prepare-input");
  expect(screen.queryByRole("button",{name:"恢复使用原始文件"})).not.toBeInTheDocument();
});

it("转录组映射可选择样本按行并提交方向", async () => {
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets: [
    {id:"expression",asset_type:"transcriptome",original_name:"转录组.csv",metadata:{asset_set:"Set2"}},
  ]} as unknown as Awaited<ReturnType<typeof projects.listProjectAssets>>);
  const post=vi.spyOn(apiClient,"post").mockResolvedValueOnce({
    sheets:[],selected_sheet:null,columns:["sample","G1","G2"],preview_rows:[["001","0.1","2"]],
  }).mockResolvedValueOnce({success:true});
  render(<InputMappingPanel projectId="p" assetSet="Set2" onSaved={vi.fn()}/>);
  openMapping();
  fireEvent.change(await screen.findByLabelText("原始数据文件"),{target:{value:"expression"}});
  expect(await screen.findByLabelText("基因编号列")).toBeInTheDocument();
  expect(screen.getByText(/整理成基因按行、样本按列/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("转录组矩阵方向"),{target:{value:"samples_are_rows"}});
  expect(screen.getByLabelText("样本编号列")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("样本编号列"),{target:{value:"sample"}});
  fireEvent.click(screen.getByRole("button",{name:"保存映射并重新检查"}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith(
    "/api/projects/p/assets/expression/prepare-input",
    {identifier_column:"sample",orientation:"samples_are_rows"},
  ));
});


it("粘贴样本编号对应，拒绝重复，恢复已保存映射并随重置清空", async () => {
  vi.spyOn(projects, "listProjectAssets").mockResolvedValue({assets: [
    {id: "profile", asset_type: "profile", original_name: "样本.csv", metadata: {asset_set: "Set2"}},
  ]} as unknown as Awaited<ReturnType<typeof projects.listProjectAssets>>);
  const aliases = [{source_sample: "RNA-001", target_sample: "001"}, {source_sample: "RNA-002", target_sample: "002"}];
  const post = vi.spyOn(apiClient, "post").mockResolvedValueOnce({
    sheets: [], selected_sheet: null, columns: ["sample", "group"], preview_rows: [["RNA-001", "A"]],
    input_preparation: {identifier_column: "sample", sample_mappings: aliases},
  }).mockResolvedValueOnce({success: true});
  const reset = vi.spyOn(apiClient, "delete").mockResolvedValue({success: true});
  const saved = vi.fn();
  render(<InputMappingPanel projectId="p" assetSet="Set2" onSaved={saved} />);
  openMapping();
  fireEvent.change(await screen.findByLabelText("原始数据文件"), {target: {value: "profile"}});
  const input = await screen.findByLabelText("样本编号对应（可选）");
  expect(input).toHaveValue("RNA-001\t001\nRNA-002\t002");
  expect(screen.getByText("编号对应预览")).toBeInTheDocument();
  const save = screen.getByRole("button", {name: "保存映射并重新检查"});
  fireEvent.change(input, {target: {value: "RNA-001\t001\nRNA-002\t001"}});
  expect(save).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("编号重复");
  fireEvent.change(input, {target: {value: "RNA-001,001"}});
  expect(save).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("第 1 行需要两列");
  fireEvent.change(input, {target: {value: "RNA-001\t001\nRNA-002\t002"}});
  fireEvent.click(save);
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenLastCalledWith("/api/projects/p/assets/profile/prepare-input", {
    identifier_column: "sample", sample_mappings: aliases,
  });
  fireEvent.click(screen.getByRole("button", {name: "恢复使用原始文件"}));
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(2));
  expect(input).toHaveValue("");
  expect(reset).toHaveBeenCalledWith("/api/projects/p/assets/profile/prepare-input");
});


it("批次三列对应允许跨批次同名，拒绝批次内重名并完整恢复与提交", async () => {
  vi.spyOn(projects, "listProjectAssets").mockResolvedValue({assets: [
    {id: "profile", asset_type: "profile", original_name: "批次样本.csv", metadata: {asset_set: "Set2"}},
  ]} as unknown as Awaited<ReturnType<typeof projects.listProjectAssets>>);
  const aliases = [
    {source_sample: "RNA-001", target_sample: "001", source_batch: "批次甲"},
    {source_sample: "RNA-001", target_sample: "001", source_batch: "批次乙"},
  ];
  const post = vi.spyOn(apiClient, "post").mockResolvedValueOnce({
    sheets: [], selected_sheet: null, columns: ["sample", "batch", "group"], preview_rows: [["RNA-001", "批次甲", "A"]],
    input_preparation: {identifier_column: "sample", batch_field: "batch", sample_mappings: aliases},
  }).mockResolvedValueOnce({success: true});
  vi.spyOn(apiClient, "delete").mockResolvedValue({success: true});
  const saved = vi.fn();
  render(<InputMappingPanel projectId="p" assetSet="Set2" onSaved={saved} />);
  openMapping();
  fireEvent.change(await screen.findByLabelText("原始数据文件"), {target: {value: "profile"}});
  const input = await screen.findByLabelText("样本编号对应（可选）");
  expect(screen.getByLabelText("输入表批次字段（可选）")).toHaveValue("batch");
  expect(input).toHaveValue("RNA-001\t001\t批次甲\nRNA-001\t001\t批次乙");
  const save = screen.getByRole("button", {name: "保存映射并重新检查"});
  expect(save).toBeEnabled();
  fireEvent.change(input, {target: {value: "RNA-001\t001\t批次甲\nRNA-002\t001\t批次甲"}});
  expect(save).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("同一批次中的编号重复");
  fireEvent.change(input, {target: {value: "RNA-001\t001"}});
  expect(screen.getByRole("alert")).toHaveTextContent("需要三列");
  fireEvent.change(input, {target: {value: "RNA-001\t001\t批次甲\nRNA-001\t001\t批次乙"}});
  fireEvent.click(save);
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenLastCalledWith("/api/projects/p/assets/profile/prepare-input", {
    identifier_column: "sample", batch_field: "batch", sample_mappings: aliases,
  });
  fireEvent.click(screen.getByRole("button", {name: "恢复使用原始文件"}));
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText("输入表批次字段（可选）")).toHaveValue("");
  expect(input).toHaveValue("");
});

it("折叠区不读取目录，展开也只整理实际所选的历史表格", async () => {
  const list=vi.spyOn(projects,"listProjectAssets");
  const old={id:"old-profile",project_id:"p",asset_type:"profile",original_name:"历史指标.csv",storage_path:"/old.csv",metadata:{asset_set:"Set2",superseded:true}} as unknown as import("../shared/types/domain").ProjectAsset;
  const post=vi.spyOn(apiClient,"post").mockResolvedValue({sheets:[],selected_sheet:null,columns:["sample"],preview_rows:[["001"]]});
  const {rerender}=render(<InputMappingPanel projectId="p" assetSet="Set2" selectedAssets={[old]} inputTypes={["profile"]} onSaved={vi.fn()}/>);
  expect(list).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("原始数据文件")).not.toBeInTheDocument();
  openMapping();
  await screen.findByRole("option",{name:"历史指标.csv"});
  fireEvent.change(screen.getByLabelText("原始数据文件"),{target:{value:old.id}});
  await screen.findByLabelText("样本编号列");
  fireEvent.change(screen.getByLabelText("样本编号列"),{target:{value:"sample"}});
  rerender(<InputMappingPanel projectId="p" assetSet="Set2" selectedAssets={[{...old,metadata:{...old.metadata,validation:{status:"valid"}}}]} inputTypes={["profile"]} onSaved={vi.fn()}/>);
  expect(screen.getByLabelText("样本编号列")).toHaveValue("sample");
  expect(post).toHaveBeenCalledWith("/api/projects/p/assets/old-profile/input-schema",{});
  expect(list).not.toHaveBeenCalled();
});

it("独立映射入口只展开后按数据集和类型取第一页，不扫描整个项目", async () => {
  const list=vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[{id:"profile",asset_type:"profile",original_name:"样本.csv",metadata:{asset_set:"Set2"}}],pagination:{page:1,total_pages:100}} as unknown as Awaited<ReturnType<typeof projects.listProjectAssets>>);
  render(<InputMappingPanel projectId="p" assetSet="Set2" inputTypes={["profile"]} onSaved={vi.fn()}/>);
  expect(list).not.toHaveBeenCalled();
  openMapping();
  await screen.findByRole("option",{name:"样本.csv"});
  expect(list).toHaveBeenCalledTimes(1);
  expect(list).toHaveBeenCalledWith("p",{page:1,pageSize:50,inputsOnly:true,assetSet:"Set2",assetType:"profile"});
});
