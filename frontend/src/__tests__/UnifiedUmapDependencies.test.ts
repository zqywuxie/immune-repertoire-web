import { describe, expect, it } from "vitest";
import { batchResultSource, orderBatchDependencies } from "../features/scripthub/batchDependencies";

describe("统一 UMAP 批次依赖", () => {
  it("VJ 组合会先运行并绑定上游 VJ 使用结果", () => {
    const modules = ["umap", "pep-analysis"];
    const sourceFor = (module: string) => batchResultSource(module, modules, (item) =>
      item === "umap" ? { analysis_mode: "unified", configurations: ["profile", "vj"] } : {},
    );

    expect(sourceFor("umap")).toBe("pep-analysis");
    expect(orderBatchDependencies(modules, sourceFor)).toEqual(["pep-analysis", "umap"]);
  });

  it("仅样本指标投影不强制依赖克隆分析", () => {
    const modules = ["umap", "pep-analysis"];
    const source = batchResultSource("umap", modules, () => ({
      analysis_mode: "unified",
      configurations: ["profile"],
    }));
    expect(source).toBeUndefined();
  });
});
