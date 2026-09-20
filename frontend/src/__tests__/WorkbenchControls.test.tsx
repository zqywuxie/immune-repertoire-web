import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Select } from "../shared/components/Select";
import { Sheet } from "../shared/components/Sheet";
import { JobDetailPanel } from "../features/jobs/JobDetailPanel";
import { getJobResults } from "../shared/api/jobs";

vi.mock("../shared/api/jobs", () => ({getJobResults:vi.fn(),getJob:vi.fn()}));
afterEach(() => {cleanup();vi.clearAllMocks();});
it("select supports arrow navigation, selection and escape focus restoration", () => {
  const change=vi.fn();
  render(<Select ariaLabel="版本" value="a" options={[{value:"a",label:"版本一"},{value:"b",label:"版本二"}]} onChange={change} />);
  const trigger=screen.getByRole("button",{name:"版本"});
  fireEvent.keyDown(trigger,{key:"ArrowDown"});
  expect(screen.getByRole("option",{name:"版本一"})).toHaveFocus();
  fireEvent.keyDown(document.activeElement!,{key:"ArrowDown"});
  expect(screen.getByRole("option",{name:"版本二"})).toHaveFocus();
  fireEvent.click(document.activeElement!);
  expect(change).toHaveBeenCalledWith("b");expect(trigger).toHaveFocus();
  fireEvent.click(trigger);fireEvent.keyDown(document.activeElement!,{key:"Escape"});
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();expect(trigger).toHaveFocus();
});
it("sheet constrains tab focus and requests close with Escape", () => {
  const close=vi.fn();render(<Sheet open title="编辑" onClose={close}><input aria-label="名称"/><button>保存</button></Sheet>);
  screen.getByText("保存").focus();fireEvent.keyDown(document.activeElement!,{key:"Tab"});
  expect(screen.getByRole("button",{name:"关闭"})).toHaveFocus();
  fireEvent.keyDown(document.activeElement!,{key:"Escape"});expect(close).toHaveBeenCalledOnce();
});
it("controlled task detail reuses provided results without making another request", () => {
  const job={id:"job-one",job_type:"analysis",module:"profile",status:"completed" as const,progress:100};
  render(<JobDetailPanel job={job} onClose={vi.fn()} result={{success:true,job,status:"completed",outputs:[{kind:"html",url:"/one.html",label:"图表报告"}],assets:[],result:{}}}/>);
  expect(screen.getByRole("link",{name:"打开交互报告"})).toHaveAttribute("href","/one.html");
  expect(getJobResults).not.toHaveBeenCalled();
});
