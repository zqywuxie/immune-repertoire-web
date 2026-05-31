"""
Sequencing Reads Bar Chart - Final Version
Reads data from Excel file and creates visualization
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import os
from matplotlib import rcParams

# 设置中文字体
rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
rcParams["axes.unicode_minus"] = False


def create_sequencing_reads_bar_chart():
    """创建测序reads条形图 - 从Excel读取数据"""

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

    # Chains to display
    chains = ["TRA", "TRB", "TRD", "TRG", "IGH", "IGK", "IGL"]

    # Extract reads and percentage data
    data = {}
    percentage_data = {}
    for sample in desired_order:
        sample_data = []
        sample_pct_data = []
        sample_row = ct_samples[ct_samples["Sample"] == sample].iloc[0]
        for chain in chains:
            sample_data.append(int(sample_row[f"{chain}_reads"]))
            sample_pct_data.append(float(sample_row[f"{chain}_percent_reads_all"]))
        data[sample] = sample_data
        percentage_data[sample] = sample_pct_data

    # Create DataFrames
    df_data = pd.DataFrame(data, index=chains)
    df_pct = pd.DataFrame(percentage_data, index=chains)

    # Print data summary
    print("CT样本测序reads数据：")
    print("=" * 100)
    print(
        f"{'Sample':<15} {'TRA':<8} {'TRB':<8} {'TRD':<8} {'TRG':<8} {'IGH':<8} {'IGK':<8} {'IGL':<8}"
    )
    print("-" * 100)
    for sample in desired_order:
        values = data[sample]
        print(
            f"{sample:<15} {values[0]:<8,} {values[1]:<8,} {values[2]:<8,} {values[3]:<8,} {values[4]:<8,} {values[5]:<8,} {values[6]:<8,}"
        )

    # Create output directory
    output_dir = "/workspace/data_shared/To_ZQY/CT_Sequencing_Reads_Chart_Final"
    os.makedirs(output_dir, exist_ok=True)

    # Save to CSV with reads and percentages combined
    csv_file = os.path.join(output_dir, "ct_samples_sequencing_reads.csv")

    # Create combined DataFrame with reads and percentages in same column
    combined_data = []
    for sample in desired_order:
        row = {"Sample": sample}
        for i, chain in enumerate(chains):
            # Format: "57270 (15.31%)"
            row[chain] = f"{data[sample][i]} ({percentage_data[sample][i]:.2f}%)"
        combined_data.append(row)

    combined_df = pd.DataFrame(combined_data)
    combined_df.to_csv(csv_file, index=False)
    print(f"\n数据已保存至: {csv_file}")

    # Create visualization
    create_visualization(df_data, desired_order, output_dir)

    print(f"\n任务完成！")
    print("=" * 60)


def create_visualization(df, samples, output_dir):
    """Create percentage change visualization with TCR and IG separated"""

    # Create visualization subdirectory
    viz_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(viz_dir, exist_ok=True)

    # Use NW_11_1030CT as baseline (index 9 in 11-sample list)
    baseline_sample = "NW_11_1030CT"
    baseline_index = 9

    # Define colors for each chain
    colors = {
        "TRA": "#1f77b4",
        "TRB": "#ff7f0e",
        "TRD": "#2ca02c",
        "TRG": "#d62728",
        "IGH": "#9467bd",
        "IGK": "#8c564b",
        "IGL": "#e377c2",
    }

    # Create TCR chains figure (TRA, TRB, TRD, TRG)
    create_tcr_figure(df, samples, baseline_sample, baseline_index, colors, viz_dir)

    # Create IG chains figure (IGH, IGK, IGL)
    create_ig_figure(df, samples, baseline_sample, baseline_index, colors, viz_dir)


def create_tcr_figure(df, samples, baseline_sample, baseline_index, colors, viz_dir):
    """Create TCR chains visualization"""

    # Create figure with 2x2 subplots
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    fig.suptitle(
        f"TCR Sequencing Reads - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
        fontsize=20,
        fontweight="bold",
        y=0.98,
    )

    # Flatten axes for easier iteration
    axes = axes.flatten()

    # TCR chains
    tcr_chains = ["TRA", "TRB", "TRD", "TRG"]

    x_pos = np.arange(len(samples))
    bar_width = 0.6

    # Plot each TCR chain
    for idx, (chain, ax) in enumerate(zip(tcr_chains, axes)):
        # Get values for this chain
        values = df.loc[chain].values

        # Get baseline value
        baseline_value = values[baseline_index]

        # Calculate percentage changes
        pct_change = (values - baseline_value) / baseline_value * 100

        # Create vertical bars
        bars = ax.bar(x_pos, pct_change, bar_width, color=colors[chain], alpha=0.8)

        # Highlight baseline bar
        bars[baseline_index].set_edgecolor("black")
        bars[baseline_index].set_linewidth(2)
        bars[baseline_index].set_alpha(1.0)

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
            if j == baseline_index:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + max(pct_change) * 0.02,
                    "Baseline",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color="red",
                )
            elif height > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + max(pct_change) * 0.02,
                    f"+{height:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    fontweight="bold",
                )
            else:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height - max(pct_change) * 0.02,
                    f"{height:.1f}%",
                    ha="center",
                    va="top",
                    fontsize=8,
                    fontweight="bold",
                )

        # Customize subplot
        ax.set_xticks(x_pos)
        ax.set_xticklabels(samples, rotation=45, ha="right", fontsize=11)
        ax.set_ylabel(
            "Percentage Change from Baseline (%)", fontsize=14, fontweight="bold"
        )
        ax.set_xlabel("CT Sample", fontsize=14, fontweight="bold")
        ax.set_title(f"{chain} Reads", fontsize=16, fontweight="bold", pad=20)
        ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
        ax.grid(axis="y", alpha=0.3, linestyle="--")

        # Set y-axis limits for percentage values
        ymin = min(pct_change) * 1.1 if min(pct_change) < 0 else -5
        ymax = max(pct_change) * 1.1 if max(pct_change) > 0 else 5
        ax.set_ylim(ymin, ymax)

        # Add background color
        ax.set_facecolor("#f8f9fa")

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    # Save the figure
    plt.savefig(
        os.path.join(viz_dir, "tcr_reads_percentage_change_11_samples.png"),
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.savefig(
        os.path.join(viz_dir, "tcr_reads_percentage_change_11_samples.pdf"),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close()

    print(f"  Saved TCR reads percentage change chart")


def create_ig_figure(df, samples, baseline_sample, baseline_index, colors, viz_dir):
    """Create IG chains visualization"""

    # Create figure with 1x3 subplots
    fig, axes = plt.subplots(1, 3, figsize=(24, 8))
    fig.suptitle(
        f"IG Sequencing Reads - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
        fontsize=20,
        fontweight="bold",
        y=0.98,
    )

    # IG chains
    ig_chains = ["IGH", "IGK", "IGL"]

    x_pos = np.arange(len(samples))
    bar_width = 0.6

    # Plot each IG chain
    for idx, (chain, ax) in enumerate(zip(ig_chains, axes)):
        # Get values for this chain
        values = df.loc[chain].values

        # Get baseline value
        baseline_value = values[baseline_index]

        # Calculate percentage changes
        pct_change = (values - baseline_value) / baseline_value * 100

        # Create vertical bars
        bars = ax.bar(x_pos, pct_change, bar_width, color=colors[chain], alpha=0.8)

        # Highlight baseline bar
        bars[baseline_index].set_edgecolor("black")
        bars[baseline_index].set_linewidth(2)
        bars[baseline_index].set_alpha(1.0)

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
            if j == baseline_index:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + max(pct_change) * 0.02,
                    "Baseline",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color="red",
                )
            elif height > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + max(pct_change) * 0.02,
                    f"+{height:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    fontweight="bold",
                )
            else:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height - max(pct_change) * 0.02,
                    f"{height:.1f}%",
                    ha="center",
                    va="top",
                    fontsize=8,
                    fontweight="bold",
                )

        # Customize subplot
        ax.set_xticks(x_pos)
        ax.set_xticklabels(samples, rotation=45, ha="right", fontsize=11)
        ax.set_ylabel(
            "Percentage Change from Baseline (%)", fontsize=14, fontweight="bold"
        )
        ax.set_xlabel("CT Sample", fontsize=14, fontweight="bold")
        ax.set_title(f"{chain} Reads", fontsize=16, fontweight="bold", pad=20)
        ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
        ax.grid(axis="y", alpha=0.3, linestyle="--")

        # Set y-axis limits for percentage values
        ymin = min(pct_change) * 1.1 if min(pct_change) < 0 else -5
        ymax = max(pct_change) * 1.1 if max(pct_change) > 0 else 5
        ax.set_ylim(ymin, ymax)

        # Add background color
        ax.set_facecolor("#f8f9fa")

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    # Save the figure
    plt.savefig(
        os.path.join(viz_dir, "ig_reads_percentage_change_11_samples.png"),
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.savefig(
        os.path.join(viz_dir, "ig_reads_percentage_change_11_samples.pdf"),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close()

    print(f"  Saved IG reads percentage change chart")


if __name__ == "__main__":
    create_sequencing_reads_bar_chart()
