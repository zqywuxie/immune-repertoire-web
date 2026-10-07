import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { Stage4Execution } from "../features/scripthub/stages/Stage4Execution";
import * as jobs from "../shared/api/jobs";
import * as api from "../shared/api/scriptHub";
import type { JobResultsResponse } from "../shared/api/jobs";
type Detail = Awaited<ReturnType<typeof jobs.getJob>>;
const item = (module: string, status: string, job_id = "", extra = {}) => ({ module, status, job_id, ...extra });
const detail = (id: string, status: string, extra = {}) => ({ success: true, job: { id, status, ...extra } }) as Detail;
const result = (id: string) => ({ success: true, job: {id, status:"completed", progress:100}, status:"completed", outputs:[], assets:[], result:{} }) as unknown as JobResultsResponse;
const config = {"pep-analysis": {group_fields:["group"], selected_group_values:{group:["A","B"]}, selected_samples_by_group:{group:{A:["A1"],B:["B1"]}}}, umapin:{category_col:"Category"}};
function Run({complete = vi.fn(), created = vi.fn()}: {complete?: (results:Record<string,JobResultsResponse>)=>void; created?: (id:string)=>void}) {
  const [ids,setIds] = useState<string[]>([]);
  return <Stage4Execution projectId="project" modules={["pep-analysis","umapin"]} baseConfig={{asset_set:"Set2"}} moduleConfigs={config} jobIds={ids} onJobsCreated={setIds} onComplete={complete} onBatchCreated={created}/>;
}
async function start() {
  await act(async () => {
    fireEvent.change(screen.getByRole("combobox"), {target:{value:"batch"}});
    fireEvent.click(screen.getByRole("button", {name:"运行所选模块"}));
  });
}
afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.useRealTimers();});
describe("组合分析实际进度", () => {
  it("读取子任务实际进度，并显示尚无编号的依赖等待项", async () => {
    vi.useFakeTimers();
    const submit = vi.spyOn(api,"submitAnalysisBatch").mockResolvedValue({success:true,job_id:"batch",status:"queued"});
    vi.spyOn(jobs,"getJob").mockImplementation(async id => id === "batch"
      ? detail("batch","running",{payload:{items:[item("pep-analysis","running","pep"),item("umapin","queued","",{depends_on:[0]})]}})
      : detail("pep","running",{progress:35,stage:"计算克隆共享"}));
    render(<Run/>); await start();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","35");
    expect(screen.getByText("计算克隆共享")).toBeInTheDocument();
    const waiting = screen.getByRole("article",{name:"第 2 项 · 特征降维"});
    expect(waiting).toHaveTextContent("等待");
    expect(waiting).toHaveTextContent("克隆共享");
    expect(within(waiting).queryByRole("progressbar")).not.toBeInTheDocument();
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it("部分结果读取失败仍保留成功结果，结束后只重新读取失败项", async () => {
    vi.useFakeTimers();
    const submit = vi.spyOn(api,"submitAnalysisBatch").mockResolvedValue({success:true,job_id:"batch",status:"queued"});
    const get = vi.spyOn(jobs,"getJob").mockImplementation(async id => id === "batch"
      ? detail("batch","completed",{payload:{items:[item("pep-analysis","completed","pep"),item("umapin","completed","umap",{depends_on:[0]})]}})
      : detail(id,"completed",{progress:100}));
    let fail = true;
    const results = vi.spyOn(jobs,"getJobResults").mockImplementation(async id => {
      if(id === "umap" && fail) throw new Error("连接中断");
      return result(id);
    });
    const complete=vi.fn(); render(<Run complete={complete}/>); await start();
    expect(complete).toHaveBeenLastCalledWith({pep:result("pep")});
    expect(screen.getByText(/此项状态或结果暂时读取失败/)).toBeInTheDocument();
    await act(async () => {await vi.advanceTimersByTimeAsync(6000);});
    expect(get.mock.calls.filter(([id]) => id === "batch")).toHaveLength(1);
    fail=false;
    await act(async () => {fireEvent.click(screen.getByRole("button",{name:"重新读取此项"}));});
    expect(complete).toHaveBeenLastCalledWith({pep:result("pep"),umap:result("umap")});
    expect(screen.queryByText(/此项状态或结果暂时读取失败/)).not.toBeInTheDocument();
    expect(submit).toHaveBeenCalledTimes(1);
    expect(results.mock.calls.filter(([id])=>id==="pep")).toHaveLength(1);
  });
  it("断线保留实际进度，恢复读取同一批次且终态停止轮询", async () => {
    vi.useFakeTimers();
    const submit=vi.spyOn(api,"submitAnalysisBatch").mockResolvedValue({success:true,job_id:"batch",status:"queued"});
    let rounds=0;
    const get=vi.spyOn(jobs,"getJob").mockImplementation(async id => {
      if(id === "batch") {
        rounds++;
        if(rounds===2) throw new Error("断线");
        return detail("batch",rounds>=3?"failed":"running",{payload:{items:[
          item("pep-analysis",rounds>=3?"failed":"running","pep"),
          item("umapin",rounds>=3?"failed":"queued","",rounds>=3?{blocked_by:[0],depends_on:[0],error:"前置分析未成功完成"}:{depends_on:[0]})
        ]}});
      }
      return detail("pep",rounds>=3?"failed":"running",{progress:35,stage:"计算克隆共享"});
    });
    vi.spyOn(jobs,"getJobResults").mockResolvedValue({...result("pep"),status:"failed",job:{...result("pep").job,status:"failed",progress:35}});
    const complete=vi.fn(); render(<Run complete={complete}/>); await start();
    await act(async()=>{await vi.advanceTimersByTimeAsync(2000);});
    expect(screen.getByRole("status",{name:"任务状态连接"})).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","35");
    await act(async()=>{await vi.advanceTimersByTimeAsync(1500);});
    expect(screen.queryByRole("status",{name:"任务状态连接"})).not.toBeInTheDocument();
    const blocked=screen.getByRole("article",{name:"第 2 项 · 特征降维"});
    expect(blocked).toHaveTextContent("前置分析未成功完成");
    expect(within(blocked).queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","35");
    expect(complete).toHaveBeenLastCalledWith(expect.objectContaining({pep:expect.objectContaining({status:"failed"})}));
    await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
    expect(get.mock.calls.filter(([id])=>id==="batch")).toHaveLength(3);
    expect(submit).toHaveBeenCalledTimes(1);
  });
  it("离开页面后不消费迟到的子结果", async () => {
    let resolve!: (value:JobResultsResponse)=>void;
    vi.spyOn(api,"submitAnalysisBatch").mockResolvedValue({success:true,job_id:"batch",status:"queued"});
    vi.spyOn(jobs,"getJob").mockImplementation(async id => id==="batch"
      ? detail("batch","completed",{payload:{items:[item("pep-analysis","completed","pep"),item("umapin","failed","",{error:"输入不匹配"})]}})
      : detail("pep","completed",{progress:100}));
    const results=vi.spyOn(jobs,"getJobResults").mockImplementation(()=>new Promise(done=>{resolve=done;}));
    const complete=vi.fn(); const view=render(<Run complete={complete}/>); await start();
    expect(results).toHaveBeenCalledTimes(1);
    view.unmount(); await act(async()=>{resolve(result("pep"));});
    expect(complete).not.toHaveBeenCalled();
  });
  it("离开页面后不处理迟到的提交响应，也不读取批次", async () => {
    let resolve!: (value:Awaited<ReturnType<typeof api.submitAnalysisBatch>>)=>void;
    vi.spyOn(api,"submitAnalysisBatch").mockImplementation(()=>new Promise(done=>{resolve=done;}));
    const get=vi.spyOn(jobs,"getJob");
    const created=vi.fn(); const view=render(<Run created={created}/>); await start();
    view.unmount(); await act(async()=>{resolve({success:true,job_id:"batch",status:"queued"});});
    expect(get).not.toHaveBeenCalled(); expect(created).not.toHaveBeenCalled();
  });
  it("子任务读数缺失时不伪造零或完成百分比", async () => {
    vi.useFakeTimers();
    vi.spyOn(api,"submitAnalysisBatch").mockResolvedValue({success:true,job_id:"batch",status:"queued"});
    vi.spyOn(jobs,"getJob").mockImplementation(async id=>id==="batch"
      ? detail("batch","running",{payload:{items:[item("pep-analysis","running","pep"),item("umapin","queued","",{depends_on:[0]})]}})
      : detail("pep","running"));
    render(<Run/>); await start();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByText("尚未读取到此项的进度记录。")).toBeInTheDocument();
  });
  it("拒绝较旧的子任务快照，保留最近实际进度", async () => {
    vi.useFakeTimers(); let reads=0;
    vi.spyOn(api,"submitAnalysisBatch").mockResolvedValue({success:true,job_id:"batch",status:"queued"});
    vi.spyOn(jobs,"getJob").mockImplementation(async id=>id==="batch"
      ? detail("batch","running",{payload:{items:[item("pep-analysis","running","pep"),item("umapin","queued","",{depends_on:[0]})]}})
      : ++reads===1 ? detail("pep","running",{progress:35,updated_at:"2026-10-03T01:00:02Z"})
        : detail("pep","running",{progress:5,updated_at:"2026-10-03T01:00:01Z"}));
    render(<Run/>); await start(); await act(async()=>{await vi.advanceTimersByTimeAsync(2000);});
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","35");
  });

});
