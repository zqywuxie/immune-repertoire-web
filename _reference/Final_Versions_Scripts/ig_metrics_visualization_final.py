"""
Extract and visualize IG metrics from Excel - Final Version
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import os
from matplotlib import rcParams

# 设置中文字体
rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
rcParams["axes.unicode_minus"] = False


def create_ig_metrics_comparison():
    """
    创建免疫球蛋白指标百分比差异对比图 - 从Excel读取数据
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

    # Extract IG metrics data
    chains = ["IGH", "IGK", "IGL"]
    metrics_data = []

    print("CT样本IG指标数据提取结果：")
    print("=" * 100)
    print(
        f"{'Sample':<15} {'Chain':<8} {'Reads':<10} {'UCDR3':<10} {'D50':<8} {'Gini index':<12} {'Shannon':<10}"
    )
    print("-" * 100)

    for _, row in ct_samples.iterrows():
        sample = row["Sample"]

        for chain in chains:
            # Extract data for each chain
            reads = int(row[f"{chain}_reads"])
            ucd_r3 = int(row[f"{chain}_ucdr3"])
            d50 = row[f"{chain}_d50"]
            gini = row[f"{chain}_Gini_index"]
            shannon = row[f"{chain}_Shannon"]

            # Add to metrics data
            metrics_data.append(
                {
                    "Sample": sample,
                    "Chain": chain,
                    "Reads": reads,
                    "UCDR3": ucd_r3,
                    "D50": d50,
                    "Gini index": gini,
                    "Shannon": shannon,
                }
            )

            # Print formatted output
            print(
                f"{sample:<15} {chain:<8} {reads:<10,} {ucd_r3:<10,} {d50:<8.2f} {gini:<12.3f} {shannon:<10.2f}"
            )

    # Create DataFrame and save
    metrics_df = pd.DataFrame(metrics_data)

    # Create output directory
    output_dir = "/workspace/data_shared/To_ZQY/CT_IG_Metrics_Analysis_Final"
    os.makedirs(output_dir, exist_ok=True)

    # Save to CSV
    csv_file = os.path.join(output_dir, "ct_samples_ig_metrics.csv")
    metrics_df.to_csv(csv_file, index=False)
    print(f"\n数据已保存至: {csv_file}")

    # Create optimized visualizations
    create_optimized_visualizations(metrics_df, output_dir, desired_order)

    print(f"\n任务完成！")
    print("=" * 60)


def create_optimized_visualizations(df, output_dir, desired_order):
    """Create optimized visualizations with baseline comparison"""

    # Create visualization subdirectory
    viz_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(viz_dir, exist_ok=True)

    # Define metrics to visualize
    metrics = ["UCDR3", "D50", "Gini index", "Shannon"]

    # Define colors (blue and orange)
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]

    # Use NW_11_1030CT as baseline (index 9 in 11-sample list)
    baseline_sample = "NW_11_1030CT"
    baseline_index = 9

    # Create separate figure for each metric
    for metric in metrics:
        # Create figure with 1x3 subplots (one for each chain)
        fig, axes = plt.subplots(1, 3, figsize=(24, 8))
        fig.suptitle(
            f"IG {metric} - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
            fontsize=20,
            fontweight="bold",
            y=0.98,
        )

        x_pos = np.arange(len(desired_order))
        bar_width = 0.6

        for idx, (chain, ax) in enumerate(zip(["IGH", "IGK", "IGL"], axes)):
            # Get values for this chain and metric
            chain_df = df[df["Chain"] == chain].set_index("Sample").loc[desired_order]
            values = chain_df[metric].values

            # Get baseline value
            baseline_value = values[baseline_index]

            # Calculate percentage changes
            if metric == "Gini index" or metric == "Shannon":
                # For Gini index and Shannon, higher values indicate more diversity
                pct_change = (values - baseline_value) / baseline_value * 100
            else:
                # For UCDR3 and D50, higher values indicate longer sequences
                pct_change = (values - baseline_value) / baseline_value * 100

            # Create vertical bars
            bars = ax.bar(
                x_pos, pct_change, bar_width, label=chain, color=colors[idx], alpha=0.8
            )

            # Highlight baseline bar (NW_11_1030CT - index 9)
            bars[9].set_alpha(1.0)
            bars[9].set_edgecolor("black")
            bars[9].set_linewidth(2)

            # Add baseline reference line at 0%
            ax.axhline(
                y=0,
                color="gray",
                linestyle="-",
                linewidth=2,
                alpha=0.8,
                label="Baseline (0%)",
            )

            # Add value labels on bars
            for j, bar in enumerate(bars):
                height = bar.get_height()
                if height >= 0:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        height + max(pct_change) * 0.02,
                        f"+{height:.1f}%",
                        ha="center",
                        va="bottom",
                        fontsize=9,
                        fontweight="bold",
                        color=colors[idx],
                    )
                else:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        height - max(pct_change) * 0.02,
                        f"{height:.1f}%",
                        ha="center",
                        va="top",
                        fontsize=9,
                        fontweight="bold",
                        color=colors[idx],
                    )

            # Customize subplot
            ax.set_xticks(x_pos)
            ax.set_xticklabels(desired_order, rotation=45, ha="right", fontsize=11)
            ax.set_ylabel(
                "Percentage Change from Baseline (%)", fontsize=14, fontweight="bold"
            )
            ax.set_xlabel("CT Sample", fontsize=14, fontweight="bold")
            ax.set_title(f"{chain} Chain", fontsize=16, fontweight="bold", pad=20)
            ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
            ax.grid(axis="y", alpha=0.3, linestyle="--")

            # Set y-axis limits for percentage values
            ymin = min(pct_change) * 1.1 if min(pct_change) < 0 else -5
            ymax = max(pct_change) * 1.1 if max(pct_change) > 0 else 5
            ax.set_ylim(ymin, ymax)

            # Add background color
            ax.set_facecolor("#f8f9fa")

        plt.tight_layout()
        plt.subplots_adjust(top=0.93)

        # Save the figure
        filename = f'ig_{metric.lower().replace(" ", "_")}_comparison_11_samples.png'
        plt.savefig(
            os.path.join(viz_dir, filename),
            dpi=300,
            bbox_inches="tight",
            facecolor="white",
        )
        plt.savefig(
            os.path.join(viz_dir, filename.replace(".png", ".pdf")),
            bbox_inches="tight",
            facecolor="white",
        )
        plt.close()

        print(f"  Saved {metric} comparison chart")

    print(f"\n所有图表已保存至: {viz_dir}")


if __name__ == "__main__":
    create_ig_metrics_comparison()
