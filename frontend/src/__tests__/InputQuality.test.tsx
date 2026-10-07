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

it("展示数值矩阵规模和异常单元格位置", () => {
  render(<InputQualityPanel quality={{
    inputs:[{
      kind:"transcriptome",label:"转录组数据",sample_count:3,sample_column:"列名（首列为基因）",
      status:"invalid",duplicate_samples:[],missing_sample_count:0,missing_fields:{},
      numeric_content:{row_count:12,column_count:3,invalid_count:2,examples:["第 4 行 / S1","第 7 行 / S2"]},
    }],
    reference_label:"转录组数据",alignments:[],warnings:[],errors:["数值区域存在异常"],
  }}/>);
  expect(screen.getByText("数值区域 12 行 × 3 列")).toBeVisible();
  expect(screen.getByText("数值核验：2 个单元格异常")).toBeVisible();
  fireEvent.click(screen.getByText("查看前五个异常位置"));
  expect(screen.getByText("第 4 行 / S1")).toBeVisible();
  expect(screen.getByText("第 7 行 / S2")).toBeVisible();
});


it("后台校验中显示等待状态且不将未知样本数显示为零", () => {
  render(<InputQualityPanel quality={{
    inputs:[{kind:"profile",label:"样本指标表",sample_count:0,sample_column:"",status:"pending",duplicate_samples:[],missing_sample_count:0,missing_fields:{}}],
    reference_label:"",alignments:[],warnings:[],errors:["输入文件正在后台校验，完成后自动更新。"],
  }}/>);
  expect(screen.getByText("正在后台校验，完成后自动更新")).toBeVisible();
  expect(screen.queryByText("识别样本 0 个")).not.toBeInTheDocument();
});
