import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { InputQualityPanel } from "../features/scripthub/InputQualityPanel";
afterEach(cleanup);
it("展示重复编号和跨输入样本差异明细", () => {
 render(<InputQualityPanel quality={{inputs:[{kind:"profile",label:"样本指标表",sample_count:2,sample_column:"sample",status:"invalid",duplicate_samples:["001"],missing_sample_count:0,missing_fields:{分组:1}}],reference_label:"样本指标表",alignments:[{kind:"transcriptome",label:"转录组数据",matched_count:1,missing_count:1,extra_count:1,missing_samples:["002"],extra_samples:["003"]}],warnings:["需要核对样本对应关系"],errors:["样本指标表存在重复样本编号"]}} />);
 expect(screen.getByRole("alert")).toHaveTextContent("重复样本编号");
 fireEvent.click(screen.getByText("查看编号"));
 expect(screen.getByText("缺少：002")).toBeVisible();
 expect(screen.getByText("多出：003")).toBeVisible();
 fireEvent.click(screen.getByText("查看字段空值"));
 expect(screen.getByText("分组：1 个空值")).toBeVisible();
});
