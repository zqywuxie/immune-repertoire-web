"""
创建适合PPT插入的测序深度差异小模块 - 最终版
从Excel读取数据，包含11个样本
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import os
from matplotlib import rcParams

# 设置中文字体
rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
rcParams["axes.unicode_minus"] = False


def create_sequencing_depth_module():
    """
    创建适合PPT插入的测序深度差异小模块
    返回紧凑的表格，显示相对于NW_11_1030CT基准样本的百分比差异
    """

    # Read data from Excel
    excel_file = "/workspace/data_shared/To_ZQY/CT/CT数据汇总.xlsx"
    df = pd.read_excel(excel_file)

    # Filter for CT samples
    ct_samples = df[df["Sample"].str.contains(r"NW_11_\d{4}CT$", regex=True, na=False)]

    # Define desired sample order (11 samples)
    desired_order = [
        "NW_11_0521CT",
        "NW_11_0618CT",
        "NW_11_0710CT",
        "NW_11_0806CT",
        "NW_11_0814CT",
        "NW_11_0819CT",
        "NW_11_0827CT",
        "NW_11_0909CT",
        "NW_11_0912CT",
        "NW_11_1030CT",
        "NW_11_1031CT",
    ]

    # Sort samples according to desired order
    ct_samples = ct_samples.set_index("Sample").loc[desired_order].reset_index()

    # Data for visualization
    data = {
        "Total Receptor RNA": ct_samples["Total_Receptor_RNA"].tolist(),
        "MigsGoodTotal": ct_samples["MigsGoodTotal"].tolist(),
        "ReadsGoodTotal": ct_samples["ReadsGoodTotal"].tolist(),
    }

    samples = desired_order
    df_data = pd.DataFrame(data, index=samples)

    # 使用NW_11_1030CT作为基准样本（索引9）
    baseline_sample = "NW_11_1030CT"
    baseline_index = 9
    baseline_values = df_data.iloc[baseline_index]

    # 计算相对于基准样本的百分比
    percentage_diff = df_data.div(baseline_values) * 100

    # 创建表格图 - 调整大小以适应11个样本，去除边距
    fig, ax = plt.subplots(1, 1, figsize=(12, 3.5))
    fig.patch.set_facecolor("none")  # 透明背景
    ax.set_facecolor("none")  # 透明背景

    # 设置图表边距为0
    plt.margins(0, 0)
    ax.set_position([0, 0, 1, 1])  # 使用整个图表区域

    # 准备表格数据
    table_data = []
    for i, sample in enumerate(samples):
        row = [sample]
        for metric in data.keys():
            diff = percentage_diff.loc[sample, metric] - 100
            if i == baseline_index:
                row.append("Baseline")
            elif diff > 0:
                row.append(f"+{diff:.1f}%")
            else:
                row.append(f"{diff:.1f}%")
        table_data.append(row)

    # 创建表格
    table = ax.table(
        cellText=table_data,
        colLabels=["Sample", "Total RNA", "MigsGood", "ReadsGood"],
        cellLoc="center",
        loc="center",
        colWidths=[0.12, 0.22, 0.22, 0.22],
    )

    # 设置表格样式
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.5)

    # 设置表头颜色
    for i in range(len(data.keys()) + 1):
        table[(0, i)].set_facecolor("#34495e")
        table[(0, i)].set_text_props(weight="bold", color="white")

    # 突出显示基准样本行
    for j in range(len(data.keys()) + 1):
        table[(baseline_index + 1, j)].set_facecolor("#ffebee")  # 浅红色背景
        table[(baseline_index + 1, j)].set_text_props(color="red", weight="bold")

    # 隐藏坐标轴
    ax.axis("off")

    plt.tight_layout(pad=0)

    return fig


def create_sequencing_depth_bar_chart():
    """
    创建条形图版本的测序深度差异
    """

    # Read data from Excel
    excel_file = "/workspace/data_shared/To_ZQY/CT/CT数据汇总.xlsx"
    df = pd.read_excel(excel_file)

    # Filter for CT samples
    ct_samples = df[df["Sample"].str.contains(r"NW_11_\d{4}CT$", regex=True, na=False)]

    # Define desired sample order (11 samples)
    desired_order = [
        "NW_11_0521CT",
        "NW_11_0618CT",
        "NW_11_0710CT",
        "NW_11_0806CT",
        "NW_11_0814CT",
        "NW_11_0819CT",
        "NW_11_0827CT",
        "NW_11_0909CT",
        "NW_11_0912CT",
        "NW_11_1030CT",
        "NW_11_1031CT",
    ]

    # Sort samples according to desired order
    ct_samples = ct_samples.set_index("Sample").loc[desired_order].reset_index()

    data = {
        "Total Receptor RNA": ct_samples["Total_Receptor_RNA"].tolist(),
        "MigsGoodTotal": ct_samples["MigsGoodTotal"].tolist(),
        "ReadsGoodTotal": ct_samples["ReadsGoodTotal"].tolist(),
    }

    df_data = pd.DataFrame(data, index=desired_order)

    # 使用NW_11_1030CT作为基准样本
    baseline_sample = "NW_11_1030CT"
    baseline_index = 9
    baseline_values = df_data.iloc[baseline_index]

    # 计算相对于基准样本的百分比
    percentage_diff = df_data.div(baseline_values) * 100 - 100

    # 创建图表
    fig, ax = plt.subplots(1, 1, figsize=(14, 6))
    fig.patch.set_facecolor("none")  # 透明背景
    ax.set_facecolor("none")  # 透明背景

    # 设置颜色
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]
    x = np.arange(len(desired_order))
    width = 0.25

    # 绘制条形图
    for i, (metric, color) in enumerate(zip(data.keys(), colors)):
        bars = ax.bar(
            x + i * width,
            percentage_diff[metric],
            width,
            label=metric,
            color=color,
            alpha=0.8,
        )

        # 突出显示基准样本
        bars[baseline_index].set_edgecolor("black")
        bars[baseline_index].set_linewidth(2)
        bars[baseline_index].set_alpha(1.0)

        # 添加数值标签
        for j, bar in enumerate(bars):
            height = bar.get_height()
            if j == baseline_index:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + 1,
                    "基准",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    fontweight="bold",
                    color="red",
                )
            elif height > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + 1,
                    f"+{height:.0f}%",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    fontweight="bold",
                )
            else:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height - 2,
                    f"{height:.0f}%",
                    ha="center",
                    va="top",
                    fontsize=8,
                    fontweight="bold",
                )

    # 添加基准线
    ax.axhline(y=0, color="red", linestyle="--", alpha=0.7, label="Baseline (0%)")

    # 设置图表
    ax.set_title(
        f"Sequencing Depth Differences (Baseline: {baseline_sample})",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Percentage Difference (%)", fontsize=12)
    ax.set_xlabel("CT Sample", fontsize=12)
    ax.set_xticks(x + width)
    ax.set_xticklabels(desired_order, rotation=45, ha="right")
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()

    return fig


# 创建并保存PPT模块
if __name__ == "__main__":
    # 自动创建输出目录
    output_dir = "CT_PPT输出模块_最终版"
    os.makedirs(output_dir, exist_ok=True)

    # 创建表格模块
    fig1 = create_sequencing_depth_module()
    fig1.savefig(
        f"{output_dir}/sequencing_depth_module_table_11_samples.png",
        dpi=300,
        bbox_inches="tight",
        facecolor="none",
        edgecolor="none",
        transparent=True,
    )
    plt.close(fig1)

    # 创建条形图模块
    fig2 = create_sequencing_depth_bar_chart()
    fig2.savefig(
        f"{output_dir}/sequencing_depth_module_bar_11_samples.png",
        dpi=300,
        bbox_inches="tight",
        facecolor="none",
        edgecolor="none",
        transparent=True,
    )
    plt.close(fig2)

    print(f"PPT模块已保存至: {output_dir}")
    print("-" * 60)
    print("生成的文件:")
    print("1. sequencing_depth_module_table_11_samples.png - 表格版本")
    print("2. sequencing_depth_module_bar_11_samples.png - 条形图版本")
