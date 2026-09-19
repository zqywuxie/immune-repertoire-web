import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { InputMappingPanel } from "../features/scripthub/InputMappingPanel";
import * as projects from "../shared/api/projects";
import { apiClient } from "../shared/api/client";
afterEach(() => {cleanup(); vi.restoreAllMocks();});
it("限定数据集，选择工作表和编号列后保存并重新检查", async () => {
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets: [
    {id:"one",asset_type:"profile",original_name:"样本.xlsx",metadata:{asset_set:"Set2"}},
    {id:"other",asset_type:"profile",original_name:"其他.csv",metadata:{asset_set:"Set1"}},
  ]} as unknown as Awaited<ReturnType<typeof projects.listProjectAssets>>);
  const post=vi.spyOn(apiClient,"post").mockResolvedValueOnce({sheets:["说明","数据"],selected_sheet:"说明",columns:["说明"],preview_rows:[]})
    .mockResolvedValueOnce({sheets:["说明","数据"],selected_sheet:"数据",columns:["编号","分组"],preview_rows:[["0001","甲"]]})
    .mockResolvedValueOnce({success:true});
  const saved=vi.fn();
  render(<InputMappingPanel projectId="p" assetSet="Set2" onSaved={saved}/>);
  await screen.findByRole("option",{name:"样本.xlsx"});
  expect(screen.queryByRole("option",{name:"其他.csv"})).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("原始数据文件"),{target:{value:"one"}});
  await screen.findByLabelText("数据工作表");
  fireEvent.change(screen.getByLabelText("数据工作表"),{target:{value:"数据"}});
  await screen.findByText("0001");
  fireEvent.change(screen.getByLabelText("样本编号列或基因编号列"),{target:{value:"编号"}});
  fireEvent.click(screen.getByRole("button",{name:"保存映射并重新检查"}));
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenLastCalledWith("/api/projects/p/assets/one/prepare-input",{identifier_column:"编号",sheet_name:"数据"});
  const reset=vi.spyOn(apiClient,"delete").mockResolvedValue({success:true,changed:true});
  fireEvent.click(screen.getByRole("button",{name:"恢复使用原始文件"}));
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(2));
  expect(reset).toHaveBeenCalledWith("/api/projects/p/assets/one/prepare-input");
  expect(screen.queryByRole("button",{name:"恢复使用原始文件"})).not.toBeInTheDocument();
});
