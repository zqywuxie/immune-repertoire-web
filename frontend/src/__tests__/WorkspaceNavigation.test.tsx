import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "../shared/components/Sidebar";
import { WorkspaceProvider } from "../shared/context/WorkspaceContext";
vi.mock("../shared/context/AuthContext", () => ({useAuth: () => ({user: {username:"测试账号", auth_mode:"session"}, logout:vi.fn()})}));
afterEach(cleanup);
it("保留管理工作台，只精简分析工具分组", () => {
  render(<MemoryRouter initialEntries={["/management"]}><WorkspaceProvider><Sidebar /></WorkspaceProvider></MemoryRouter>);
  for (const label of ["项目概览", "项目管理", "样本管理", "工作台设置"]) expect(screen.getByRole("link", {name:label})).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name:"分析工作台"}));
  const group = screen.getByRole("button", {name:"分析工具"}).parentElement!;
  expect(within(group).getAllByRole("link").map(link => link.textContent)).toEqual(["分析中心", "任务与结果"]);
  expect(screen.getByRole("link", {name:"分析设置"})).toBeInTheDocument();
  expect(screen.getByRole("link", {name:"账号信息"})).toBeInTheDocument();
  expect(screen.queryByRole("link", {name:/PDF|PPT|统计比较/})).not.toBeInTheDocument();
});
