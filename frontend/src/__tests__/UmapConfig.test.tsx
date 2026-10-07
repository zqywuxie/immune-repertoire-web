import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UmapConfig } from "../features/scripthub/modules/UmapConfig";
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("统一 UMAP 配置", () => {
  beforeEach(() => {
    const inspected = {
      success: true,
      suggested_sample_column: "Sample",
      suggested_group_column: "Disease",
      batch_column_candidates: ["Batch"],
      suggested_param_begin: "V1",
      suggested_param_over: "V8",
      vj_usage_path: "/results/vj.csv",
      vj_usage_available: true,
    };
    vi.stubGlobal("fetch", vi.fn(async (url: unknown) => new Response(JSON.stringify(
      String(url).endsWith("/inspect") ? inspected : { success: true, values: [], samples_by_value: {}, candidates: [] }
    ), { status: 200, headers: { "content-type": "application/json" } })));
  });

  it("展示可用数据组合并提交 VJ + 样本指标组合", async () => {
    const onChange = vi.fn();
    render(
      <UmapConfig
        projectId="project-test"
        module="umap"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          projectId: "project-test",
          profilePath: "/data/profile.csv",
          profileFields: ["Sample", "Batch", "Disease", "V1", "V8"],
          groupFields: ["Disease"],
          pepPaths: [],
          sampleNames: [],
          chains: [],
          pepColumns: [],
        }}
        value={{ analysis_mode: "unified", configurations: ["profile"] }}
        onChange={onChange}
      />,
    );

    const vjCombined = await screen.findByLabelText("指标表 + V/J 使用结果");
    await waitFor(() => expect(vjCombined).not.toBeDisabled());
    fireEvent.click(vjCombined);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      analysis_mode: "unified",
      configurations: ["profile", "vj+profile"],
    }));
    fireEvent.change(screen.getByLabelText("批次字段（可选）"), { target: { value: "Batch" } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ batch_field: "Batch" }));
    expect(screen.getByText(/PERMANOVA 置换次数/)).toBeInTheDocument();
  });
});
