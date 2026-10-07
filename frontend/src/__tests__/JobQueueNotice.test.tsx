import {afterEach,expect,it,vi} from "vitest";
import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {JobQueueNotice} from "../features/jobs/JobQueueNotice";
import {apiClient} from "../shared/api/client";
const queue={state:"busy",message:"当前工作进程都在执行任务，本任务等待计算资源释放。",position:3,online_workers:2,busy_workers:2,checked_at:"2026-10-06T00:00:00Z"};
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it("队列连接失败保留最近事实，重读不会提交计算",async()=>{
 const get=vi.spyOn(apiClient,"get").mockResolvedValueOnce({job:{status:"queued",queue_status:queue}}).mockRejectedValueOnce(new Error("断网"))
 .mockResolvedValueOnce({job:{status:"queued",queue_status:{...queue,state:"no_workers",online_workers:0,busy_workers:0,message:"当前队列没有已注册的工作进程"}}});
 const post=vi.spyOn(apiClient,"post");render(<JobQueueNotice jobId="task-1"/>);
 expect(await screen.findByText(queue.message)).toBeVisible();expect(screen.getByText(/等待队列第 3 项/)).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"重新读取队列"}));
 expect(await screen.findByRole("status")).toHaveTextContent("已保留最近记录");expect(screen.getByText(queue.message)).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"重新读取队列"}));await screen.findByText("当前队列没有已注册的工作进程");
 expect(get).toHaveBeenCalledTimes(3);expect(post).not.toHaveBeenCalled();
});
it("任务切换不会显示旧任务的迟到队列信息",async()=>{
 let resolve!:(value:unknown)=>void;
 const get=vi.spyOn(apiClient,"get").mockImplementationOnce(()=>new Promise(done=>{resolve=done;})).mockResolvedValueOnce({job:{status:"queued",queue_status:{...queue,message:"新任务已登记"}}});
 const view=render(<JobQueueNotice jobId="old"/>);await waitFor(()=>expect(get).toHaveBeenCalledTimes(1));
 view.rerender(<JobQueueNotice jobId="new"/>);await screen.findByText("新任务已登记");
 await act(async()=>resolve({job:{status:"queued",queue_status:queue}}));expect(screen.queryByText(queue.message)).not.toBeInTheDocument();
 expect(get).toHaveBeenLastCalledWith("/api/jobs/new",undefined,{skipCache:true,deduplicate:false});
});
