"""
Extract and visualize CT sequencing depth data from Excel - Final Version
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import os
from matplotlib import rcParams

# 设置中文字体
rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
rcParams["axes.unicode_minus"] = False


def extract_sequencing_data_from_excel():
    """Extract sequencing data from Excel file"""

    # Read the Excel file
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

    print(f"Found {len(ct_samples)} CT samples")

    # Extract sequencing metrics
    sequencing_data = []

    print("\nCT样本测序数据提取结果：")
    print("=" * 100)
    print(
        f"{'Sample':<15} {'Total RNA':<12} {'Reads/UMI':<10} {'MigsGood':<12} {'ReadsGood':<12} {'QC Rate':<8} {'Util Rate':<9}"
    )
    print("-" * 100)

    for _, row in ct_samples.iterrows():
        sample = row["Sample"]

        # Extract sequencing metrics
        total_rna = int(row["Total_Receptor_RNA"])
        reads_umi = row["Reads/UMI"]
        migs_good = int(row["MigsGoodTotal"])
        reads_good = int(row["ReadsGoodTotal"])

        # Calculate quality metrics
        qc_rate = migs_good / total_rna * 100
        utilization_rate = reads_good / total_rna * 100

        # Add to data list
        sequencing_data.append(
            {
                "Sample": sample,
                "Total_Receptor_RNA": total_rna,
                "Reads_per_UMI": reads_umi,
                "MigsGood_Total": migs_good,
                "ReadsGood_Total": reads_good,
                "QC_Rate": qc_rate,
                "Utilization_Rate": utilization_rate,
            }
        )

        # Print formatted output
        print(
            f"{sample:<15} {total_rna:<12,} {reads_umi:<10.2f} {migs_good:<12,} {reads_good:<12,} {qc_rate:<8.1f}% {utilization_rate:<9.1f}%"
        )

    # Create DataFrame
    sequencing_df = pd.DataFrame(sequencing_data)

    # Create output directory
    output_dir = "/workspace/data_shared/To_ZQY/CT_Sequencing_Analysis_Final"
    os.makedirs(output_dir, exist_ok=True)

    # Save to CSV
    csv_file = os.path.join(output_dir, "ct_samples_sequencing_data_11.csv")
    sequencing_df.to_csv(csv_file, index=False)
    print(f"\n数据已保存至: {csv_file}")

    # Create optimized visualizations
    create_optimized_sequencing_visualizations(sequencing_df, output_dir, desired_order)

    print(f"\n任务完成！")
    print("=" * 60)


def create_optimized_sequencing_visualizations(df, output_dir, desired_order):
    """Create optimized visualizations with baseline comparison"""

    # Create visualization subdirectory
    viz_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(viz_dir, exist_ok=True)

    # Define colors for each metric
    colors = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
    ]  # 6 colors for 6 metrics

    # Use NW_11_1030CT as baseline (index 9 in 11-sample list)
    baseline_sample = "NW_11_1030CT"
    baseline_index = 9

    # Create four-panel chart for main sequencing metrics
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    fig.suptitle(
        f"Sequencing Metrics - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
        fontsize=20,
        fontweight="bold",
        y=0.98,
    )

    x_pos = np.arange(len(desired_order))
    bar_width = 0.6

    # Define metrics to visualize
    metrics = [
        ("Total_Receptor_RNA", "Total Receptor RNA"),
        ("Reads_per_UMI", "Reads/UMI"),
        ("MigsGood_Total", "MigsGood Total"),
        ("ReadsGood_Total", "ReadsGood Total"),
    ]

    # Plot main metrics
    for idx, ((metric_key, metric_name), ax) in enumerate(zip(metrics, axes.flatten())):
        # Get values
        values = df[metric_key].values
        baseline_value = values[baseline_index]

        # Calculate percentage changes
        pct_change = (values - baseline_value) / baseline_value * 100

        # Create vertical bars with unique color for each metric
        bars = ax.bar(x_pos, pct_change, bar_width, color=colors[idx], alpha=0.8)

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
        ax.set_title(metric_name, fontsize=16, fontweight="bold", pad=20)
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
    plt.savefig(
        os.path.join(viz_dir, "sequencing_metrics_four_panel_11_samples.png"),
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.savefig(
        os.path.join(viz_dir, "sequencing_metrics_four_panel_11_samples.pdf"),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close()

    # Create quality metrics comparison
    fig, axes = plt.subplots(1, 2, figsize=(20, 8))
    fig.suptitle(
        f"Quality Metrics - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
        fontsize=20,
        fontweight="bold",
        y=0.98,
    )

    quality_metrics = [("QC_Rate", "QC Rate"), ("Utilization_Rate", "Utilization Rate")]

    for idx, ((metric_key, metric_name), ax) in enumerate(
        zip(quality_metrics, axes.flatten())
    ):
        # Get values
        values = df[metric_key].values
        baseline_value = values[baseline_index]

        # Calculate percentage changes
        pct_change = (values - baseline_value) / baseline_value * 100

        # Create vertical bars with unique color for each metric
        bars = ax.bar(x_pos, pct_change, bar_width, color=colors[idx + 4], alpha=0.8)

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
                    color=colors[idx + 4],
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
                    color=colors[idx + 4],
                )

        # Customize subplot
        ax.set_xticks(x_pos)
        ax.set_xticklabels(desired_order, rotation=45, ha="right", fontsize=11)
        ax.set_ylabel(
            "Percentage Change from Baseline (%)", fontsize=14, fontweight="bold"
        )
        ax.set_xlabel("CT Sample", fontsize=14, fontweight="bold")
        ax.set_title(metric_name, fontsize=16, fontweight="bold", pad=20)
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
    plt.savefig(
        os.path.join(viz_dir, "quality_metrics_comparison_11_samples.png"),
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.savefig(
        os.path.join(viz_dir, "quality_metrics_comparison_11_samples.pdf"),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close()

    print(f"  Saved sequencing metrics four panel chart (11 samples)")
    print(f"  Saved quality metrics comparison chart (11 samples)")

    print(f"\n所有图表已保存至: {viz_dir}")


if __name__ == "__main__":
    extract_sequencing_data_from_excel()
