import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useJobEvents } from "../shared/hooks/useJobEvents";

class ControlledSource extends EventTarget {
  static sources: ControlledSource[] = [];
  close = vi.fn();
  constructor(public url: string) { super(); ControlledSource.sources.push(this); }
  send(status: string, updated_at: string, jobId="job-1") {
    this.dispatchEvent(new MessageEvent("update", {data: JSON.stringify({success:true,status,job:{id:jobId,job_type:"script_hub",module:"profile",status,updated_at,progress:status==="running"?40:100}})}));
  }
}
beforeEach(()=>{ControlledSource.sources=[];vi.stubGlobal("EventSource",ControlledSource)});
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
it("忽略更旧的实时快照并在中断终态关闭连接",()=>{
  const hook=renderHook(()=>useJobEvents("job-1"));const source=ControlledSource.sources[0];
  act(()=>source.dispatchEvent(new Event("open")));expect(hook.result.current.connected).toBe(true);
  act(()=>source.send("running","2026-10-03T00:20:00Z"));
  act(()=>source.send("running","2026-10-03T00:19:00Z"));
  expect(hook.result.current.event?.job.updated_at).toBe("2026-10-03T00:20:00Z");
  act(()=>source.send("interrupted","2026-10-03T00:21:00Z"));
  expect(source.close).toHaveBeenCalledOnce();expect(hook.result.current.connected).toBe(false);
  act(()=>{source.dispatchEvent(new Event("error"));source.send("running","2026-10-03T00:22:00Z")});
  expect(hook.result.current.error).toBeNull();expect(hook.result.current.event?.status).toBe("interrupted");
});
it("切换任务后旧连接的状态、打开和错误回调不能污染新任务",()=>{
  const hook=renderHook(({id})=>useJobEvents(id),{initialProps:{id:"job-1"}});const old=ControlledSource.sources[0];
  act(()=>old.dispatchEvent(new Event("open")));hook.rerender({id:"job-2"});
  expect(old.close).toHaveBeenCalledOnce();expect(hook.result.current.connected).toBe(false);
  act(()=>{old.dispatchEvent(new Event("open"));old.dispatchEvent(new Event("error"));old.send("completed","2026-10-03T00:21:00Z")});
  expect(hook.result.current.connected).toBe(false);expect(hook.result.current.error).toBeNull();expect(hook.result.current.event).toBeNull();
  act(()=>ControlledSource.sources[1].send("running","2026-10-03T00:22:00Z","job-2"));
  expect(hook.result.current.event?.job.id).toBe("job-2");
});
it("同一连接断开后打开时恢复，不把其他任务的事件当作当前任务",()=>{
  const hook=renderHook(()=>useJobEvents("job-1"));const source=ControlledSource.sources[0];
  act(()=>source.dispatchEvent(new Event("error")));expect(hook.result.current.error).toBe("任务状态连接已断开。");
  act(()=>source.dispatchEvent(new Event("open")));expect(hook.result.current.error).toBeNull();expect(hook.result.current.connected).toBe(true);
  act(()=>source.send("completed","2026-10-03T00:21:00Z","other-job"));expect(source.close).not.toHaveBeenCalled();expect(hook.result.current.event).toBeNull();
});
