import { expect, it } from "vitest";
import { legacyScriptHubTaskToResults } from "../shared/api/scriptHub";

it("导出旧版任务时保留真实输入、配置、运行环境和进度记录", () => {
  const config = {selected_infiltration_samples:["甲::001", "乙::001"],group_field:"group"};
  const inputs = [{asset_id:"raw-upload",path:"/data/profile.csv"}];
  const runtime = {system:"Linux",python:"3.12"};
  const history = [{stage:"分析完成",progress:100}];
  const result = legacyScriptHubTaskToResults({
    success:true,job_id:"script_task_real",task_id:"script_task_real",module:"immune-infiltration",status:"completed",
    payload:{asset_set:"Set1",runtime},config_json:config,input_assets:inputs,analysis_signature:"real-signature",history,
    result:{metadata:{sample_count:2},csv_urls:["/data/input.csv"]},
  });
  expect(result.job.payload).toMatchObject({asset_set:"Set1",config_json:config,input_assets:inputs,runtime,analysis_signature:"real-signature"});
  expect(result.job.payload?.history).toEqual(history);
  expect(result.result.metadata).toEqual({sample_count:2});
});

it("旧版轮询结果保留取消中状态", () => {
  const result = legacyScriptHubTaskToResults({success:true,job_id:"pending",task_id:"pending",status:"running",cancel_requested:true,progress:25,stage:"正在取消"});
  expect(result.job.cancel_requested).toBe(true);
  expect(result.status).toBe("running");
  expect(result.job.progress).toBe(25);
});
