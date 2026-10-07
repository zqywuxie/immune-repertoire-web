import { useState } from "react";
import { submitLegacyScriptHubJob } from "../shared/api/scriptHub";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MlAnalysisConfig } from "../features/scripthub/modules/MlAnalysisConfig";
import { configurationIssue } from "../features/scripthub/configurationValidation";

describe("ML grouped validation configuration", () => {
  it("submits multiple selected classifier models", () => {
    const onChange = vi.fn();
    render(
      <MlAnalysisConfig
        projectId="project-test"
        module="ml-analysis"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          pepPaths: [],
          sampleNames: [],
          chains: [],
          profileFields: ["Sample", "Disease"],
          groupFields: ["Disease"],
          pepColumns: [],
        }}
        value={{ label_col: "Disease" }}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByLabelText("逻辑回归（L2）"));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      model_keys: ["random_forest", "logistic_l2"],
    }));
  });

  it("submits the selected subject column for grouped cross-validation", () => {
    const onChange = vi.fn();
    render(
      <MlAnalysisConfig
        projectId="project-test"
        module="ml-analysis"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          pepPaths: [],
          sampleNames: [],
          chains: [],
          profileFields: ["Sample", "Disease", "Subject"],
          groupFields: ["Disease", "Subject"],
          pepColumns: [],
        }}
        value={{ label_col: "Disease" }}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("受试者分组列（可选）"), {
      target: { value: "Subject" },
    });

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ group_col: "Subject" }));
  });

  it("submits stability selection settings and lets users disable final feature filtering", () => {
    const onChange = vi.fn();
    render(
      <MlAnalysisConfig
        projectId="project-test"
        module="ml-analysis"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          pepPaths: [],
          sampleNames: [],
          chains: [],
          profileFields: ["Sample", "Disease"],
          groupFields: ["Disease"],
          pepColumns: [],
        }}
        value={{ label_col: "Disease" }}
        onChange={onChange}
      />,
    );

    expect(screen.getByLabelText(/按交叉验证折中的入选频率确定最终模型特征/)).toBeChecked();
    fireEvent.change(screen.getByLabelText("最低入选频率"), { target: { value: "0.8" } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ stability_threshold: 0.8 }));

    fireEvent.click(screen.getByLabelText(/按交叉验证折中的入选频率确定最终模型特征/));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ use_stability_selection: false }));
  });
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const batchSource = { projectId: "synthetic", assetSetId: "Set2", profilePath: "/data/profile.csv", pepPaths: [],
  sampleNames: ["001"], chains: ["TRB"], profileFields: ["sample", "label", "subject", "batch", "signal", "noise"],
  groupFields: ["label", "subject", "batch"], pepColumns: [] };
const reply = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
const batchChoices = { success: true, values: ["01"], samples_by_value: { "01": ["甲::001", "乙::001"] },
  sample_labels: { "甲::001": "甲 / 001", "乙::001": "乙 / 001" }, sample_ids: { "甲::001": "001", "乙::001": "001" } };
const inspected = { success: true, sample_col: "sample", label_col: "label", suggested_param_begin: "signal",
  suggested_param_over: "noise", usage_feature_candidates: [{ value: "TRB__TRBV1", label: "TRBV1" }] };
const initialBatch = { mode: "profile", label_col: "label", batch_field: "batch", group_sample_identity: "batch_sample",
  selected_group_values: { label: ["01"] }, group_col: "subject" };
function BatchHarness({ initial = initialBatch, observe = vi.fn() }: { initial?: Record<string, unknown>; observe?: (value: Record<string, unknown>) => void }) {
  const [value, setValue] = useState<Record<string, unknown>>(initial);
  return <MlAnalysisConfig projectId="synthetic" module="ml-analysis" groupSpecs={[]} loadingSpecs={false}
    sourceContext={batchSource} value={value} onChange={next => { setValue(next); observe(next); }} />;
}

describe("ML actual batch selection and input inspection", () => {
  it("keeps subject grouping while selecting a single same-ID batch and submitting", async () => {
    const fetched = vi.fn(async (url: unknown, _init?: RequestInit) => reply(String(url).endsWith("/inspect") ? inspected
      : String(url).endsWith("/jobs") ? { success: true, task_id: "synthetic-job" } : batchChoices));
    vi.stubGlobal("fetch", fetched);
    const observe = vi.fn(); render(<BatchHarness observe={observe} />);
    const first = await screen.findByRole("button", { name: "甲 / 001" });
    await waitFor(() => expect(first).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(first);
    const payload = observe.mock.calls.at(-1)?.[0];
    expect(payload).toMatchObject({ batch_field: "batch", group_col: "subject", group_sample_identity: "batch_sample",
      selected_samples_by_group: { label: { "01": ["乙::001"] } } });
    await submitLegacyScriptHubJob({ module: "ml-analysis", projectId: "synthetic", payload: { ...payload, profile_path: batchSource.profilePath, asset_set: batchSource.assetSetId } });
    const submitted = JSON.parse(String(fetched.mock.calls.at(-1)?.[1]?.body));
    expect(screen.queryByLabelText("p 值阈值")).not.toBeInTheDocument();
    expect(submitted.selected_samples).toBeUndefined();
    expect(submitted.selected_samples_by_group).toEqual(payload.selected_samples_by_group);
    fireEvent.change(screen.getByLabelText("批次字段（可选）"), { target: { value: "" } });
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ batch_field: "", group_col: "subject", group_sample_identity: "sample" }));
    expect(observe.mock.calls.at(-1)?.[0].selected_samples_by_group).toBeUndefined();
    expect(screen.queryByDisplayValue("Selected project Profile")).not.toBeInTheDocument();
  });

  it("does not overwrite edited parameters when inspection is delayed", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn((url: unknown) => String(url).endsWith("/inspect")
      ? new Promise<Response>(done => { resolve = done; }) : Promise.resolve(reply(batchChoices))));
    const observe = vi.fn(); render(<BatchHarness observe={observe} />);
    await screen.findByRole("button", { name: "甲 / 001" });
    fireEvent.change(screen.getByLabelText("输出名称"), { target: { value: "自定义输出" } });
    fireEvent.click(screen.getByRole("button", { name: "甲 / 001" }));
    await act(async () => resolve(reply(inspected)));
    expect(screen.getByLabelText("输出名称")).toHaveValue("自定义输出");
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ output_name: "自定义输出",
      selected_samples_by_group: { label: { "01": ["乙::001"] } }, param_begin: "signal", param_over: "noise" }));
  });

  it("inspects the selected upstream artifact and uses the returned feature values", async () => {
    const fetched = vi.fn(async (url: unknown, _init?: RequestInit) => reply(String(url).includes("pep-cache-candidates")
      ? { success: true, candidates: [{ id: "artifact", artifact_id: "artifact", path: "/results/df_VJ_all.csv", job_id: "source-job", status: "available" }] }
      : String(url).endsWith("/inspect") ? inspected : batchChoices));
    vi.stubGlobal("fetch", fetched);
    const observe = vi.fn(); render(<BatchHarness initial={{ ...initialBatch, mode: "vj", upstream_artifact_id: "artifact" }} observe={observe} />);
    expect(await screen.findByRole("button", { name: "TRB__TRBV1" })).toBeInTheDocument();
    const request = fetched.mock.calls.find(([url]) => String(url).endsWith("/inspect"));
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({ asset_set: "Set2", upstream_artifact_id: "artifact", batch_field: "batch", group_col: "subject" });
    expect(JSON.parse(String(request?.[1]?.body)).usage_path).toBeUndefined();
    expect(observe.mock.calls.at(-1)?.[0].param_begin).toBeUndefined();
    expect(observe.mock.calls.at(-1)?.[0].param_over).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "TRB__TRBV1" }));
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ usage_feature_cols: ["TRB__TRBV1"] }));
  });
});


it("机器学习检查中撤销旧就绪，成功后保留模型、零值和样本选择", async () => {
  let resolve!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn((url: unknown) => String(url).endsWith("/inspect")
    ? new Promise<Response>(done => { resolve = done; }) : Promise.resolve(reply(batchChoices))));
  const observe = vi.fn();
  render(<BatchHarness initial={{ ...initialBatch, ml_inspect_ok: true }} observe={observe} />);
  await waitFor(() => expect(observe.mock.calls.at(-1)?.[0].ml_inspect_ok).toBe(false));
  const sample = await screen.findByRole("button", { name: "甲 / 001" });
  await waitFor(() => expect(sample).toHaveAttribute("aria-pressed", "true"));
  expect(configurationIssue("ml-analysis", observe.mock.calls.at(-1)![0])).toMatch(/完成.*检查/);
  fireEvent.click(sample);
  fireEvent.change(screen.getByLabelText("输出名称"), { target: { value: "保留训练条件" } });
  fireEvent.change(screen.getByLabelText("特征重要性阈值"), { target: { value: "0" } });
  fireEvent.click(screen.getByLabelText("逻辑回归（L2）"));
  await act(async () => resolve(reply(inspected)));
  await waitFor(() => expect(observe.mock.calls.at(-1)?.[0].ml_inspect_ok).toBe(true));
  expect(observe.mock.calls.at(-1)?.[0]).toMatchObject({ output_name: "保留训练条件", custom_threshold: 0,
    model_keys: ["random_forest", "logistic_l2"], selected_samples_by_group: { label: { "01": ["乙::001"] } } });
  expect(configurationIssue("ml-analysis", observe.mock.calls.at(-1)![0])).toBe("");
});

it("机器学习网络失败可重查同一来源，不提交任务且保留原参数", async () => {
  let attempts = 0;
  const fetched = vi.fn(async (url: unknown) => {
    if (!String(url).endsWith("/inspect")) return reply(batchChoices);
    if (++attempts === 1) throw new TypeError("Failed to fetch");
    return reply(inspected);
  });
  vi.stubGlobal("fetch", fetched);
  const observe = vi.fn();
  render(<BatchHarness initial={{ ...initialBatch, ml_inspect_ok: true, output_name: "保留配置", custom_threshold: 0 }} observe={observe} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("网络连接中断，请重新检查。");
  expect(configurationIssue("ml-analysis", observe.mock.calls.at(-1)![0])).toMatch(/完成.*检查/);
  fireEvent.click(screen.getByRole("button", { name: "重新检查输入" }));
  await waitFor(() => expect(observe.mock.calls.at(-1)?.[0].ml_inspect_ok).toBe(true));
  expect(observe.mock.calls.at(-1)?.[0]).toMatchObject({ output_name: "保留配置", custom_threshold: 0 });
  expect(attempts).toBe(2);
  expect(fetched.mock.calls.filter(([url]) => String(url).endsWith("/jobs"))).toHaveLength(0);
  expect(configurationIssue("ml-analysis", { ...observe.mock.calls.at(-1)![0], mode: "vj", ml_inspect_ok: false }, true)).toBe("");
});

it("更换机器学习模式后旧响应不能解除当前检查失败", async () => {
  let resolveOld!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn((url: unknown, init?: RequestInit) => {
    if (!String(url).endsWith("/inspect")) return Promise.resolve(reply(String(url).includes("pep-cache-candidates")
      ? { success: true, candidates: [] } : batchChoices));
    const payload = JSON.parse(String(init?.body));
    if (payload.mode === "profile") return new Promise<Response>(done => { resolveOld = done; });
    return Promise.resolve(new Response(JSON.stringify({ message: "当前 V/J 来源检查失败" }), { status: 400,
      headers: { "content-type": "application/json" } }));
  }));
  const observe = vi.fn(); render(<BatchHarness observe={observe} />);
  fireEvent.change(screen.getByLabelText("数据模式"), { target: { value: "vj" } });
  expect(await screen.findByRole("alert")).toHaveTextContent("当前 V/J 来源检查失败");
  await act(async () => resolveOld(reply(inspected)));
  expect(observe.mock.calls.at(-1)?.[0]).toMatchObject({ mode: "vj", ml_inspect_ok: false });
  expect(screen.getByRole("alert")).toHaveTextContent("当前 V/J 来源检查失败");
  expect(screen.queryByRole("button", { name: "TRB__TRBV1" })).not.toBeInTheDocument();
});
