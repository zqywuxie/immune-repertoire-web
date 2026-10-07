import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "../shared/components/Sidebar";
import { WorkspaceProvider } from "../shared/context/WorkspaceContext";
vi.mock("../shared/context/AuthContext", () => ({useAuth: () => ({user: {username:"测试账号", auth_mode:"session"}, logout:vi.fn()})}));
afterEach(cleanup);
it("保留管理工作台，只精简分析工具分组", () => {
  render(<MemoryRouter initialEntries={["/management"]}><WorkspaceProvider><Sidebar /></WorkspaceProvider></MemoryRouter>);
  for (const label of ["项目概览", "项目管理", "样本登记", "工作台设置"]) expect(screen.getByRole("link", {name:label})).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name:"分析工作台"}));
  const group = screen.getByRole("button", {name:"分析工具"}).parentElement!;
  expect(within(group).getAllByRole("link").map(link => link.textContent)).toEqual(["分析中心", "任务与结果"]);
  expect(screen.getByRole("link", {name:"分析设置"})).toBeInTheDocument();
  expect(screen.getByRole("link", {name:"账号信息"})).toBeInTheDocument();
  expect(screen.queryByRole("link", {name:/PDF|PPT|统计比较/})).not.toBeInTheDocument();
});

it("从明确文件入口切换侧栏工具时保留文件版本和来源地址",()=>{
 const source="/management/projects/p1?tab=assets&history=true&file_page=3&asset=old";
 render(<MemoryRouter initialEntries={[`/analysis/center?project=p1&asset_set=甲&input_asset=old&return_to=${encodeURIComponent(source)}`]}><WorkspaceProvider><Sidebar/></WorkspaceProvider></MemoryRouter>);
 const tool=screen.getByRole("link",{name:"组库指标与分组比较"});
 const target=new URL(tool.getAttribute("href")!,"http://fixture");
 expect(target.searchParams.get("input_asset")).toBe("old");
 expect(target.searchParams.get("asset_set")).toBe("甲");
 expect(target.searchParams.get("return_to")).toBe(source);
 fireEvent.click(screen.getByRole("button",{name:"分析工作台"}));
 const center=new URL(screen.getByRole("link",{name:"分析中心"}).getAttribute("href")!,"http://fixture");
 expect(center.searchParams.get("input_asset")).toBe("old");
});
