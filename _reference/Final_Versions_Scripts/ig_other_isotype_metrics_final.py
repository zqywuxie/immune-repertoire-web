"""
Extract and visualize IG other isotype metrics from Excel - Final Version
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
from pathlib import Path

# Create output directory
output_dir = "/workspace/data_shared/To_ZQY/IG_Other_Isotype_Analysis_Final"
os.makedirs(output_dir, exist_ok=True)

# Set style for publication-quality plots
plt.style.use("default")
sns.set_palette("husl")


def extract_ig_other_isotype_data():
    """Extract IG other isotype data from Excel file"""

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

    # Extract IG other isotype metrics
    ig_other_data = []

    print("\nCT样本IG其他亚型指标提取结果：")
    print("=" * 120)
    print(f"{'Sample':<15} {'IGHA':<8} {'IGHG12':<8} {'IGHG34':<8} {'IGHM/IGHD':<8}")
    print("-" * 120)

    for _, row in ct_samples.iterrows():
        sample = row["Sample"]

        # Extract IG other isotype metrics
        igha_other = row["IGHA_observed_as_other_isotype"]
        ighg12_other = row["IGHG12_observed_as_other_isotype"]
        ighg34_other = row["IGHG34_observed_as_other_isotype"]
        ighm_ighd_other = row["IGHM_IGHD_observed_as_other_isotype"]

        # Add to data list
        ig_other_data.append(
            {
                "Sample": sample,
                "IGHA_as_other": igha_other,
                "IGHG12_as_other": ighg12_other,
                "IGHG34_as_other": ighg34_other,
                "IGHM_IGHD_as_other": ighm_ighd_other,
            }
        )

        # Print formatted output
        print(
            f"{sample:<15} {igha_other:<8.2f} {ighg12_other:<8.2f} {ighg34_other:<8.2f} {ighm_ighd_other:<8.2f}"
        )

    # Create DataFrame
    ig_other_df = pd.DataFrame(ig_other_data)

    # Save to CSV
    csv_file = os.path.join(output_dir, "ct_samples_ig_other_isotype_metrics.csv")
    ig_other_df.to_csv(csv_file, index=False)
    print(f"\n数据已保存至: {csv_file}")

    # Create optimized visualizations
    create_optimized_visualizations(ig_other_df, output_dir, desired_order)

    print(f"\n任务完成！")
    print("=" * 60)


def create_optimized_visualizations(df, output_dir, desired_order):
    """Create optimized visualizations with baseline comparison"""

    # Create visualization subdirectory
    viz_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(viz_dir, exist_ok=True)

    # Get metrics and labels
    metrics = [
        "IGHA_as_other",
        "IGHG12_as_other",
        "IGHG34_as_other",
        "IGHM_IGHD_as_other",
    ]
    metric_labels = ["IGHA", "IGHG12", "IGHG34", "IGHM/IGHD"]
    colors = ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D"]

    # Use NW_11_1030CT as baseline (index 9 in 11-sample list)
    baseline_sample = "NW_11_1030CT"
    baseline_index = 9

    # Create four-panel chart
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    fig.suptitle(
        f"IG Other Isotype Metrics - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
        fontsize=20,
        fontweight="bold",
        y=0.98,
    )

    x_pos = np.arange(len(desired_order))
    bar_width = 0.6

    # Plot each metric
    for idx, (metric, label, color, ax) in enumerate(
        zip(metrics, metric_labels, colors, axes.flatten())
    ):
        # Get values
        values = df[metric].values
        baseline_value = values[baseline_index]

        # Calculate percentage changes
        pct_change = (values - baseline_value) / baseline_value * 100

        # Create vertical bars
        bars = ax.bar(x_pos, pct_change, bar_width, color=color, alpha=0.8)

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
                    color=color,
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
                    color=color,
                )

        # Customize subplot
        ax.set_xticks(x_pos)
        ax.set_xticklabels(desired_order, rotation=45, ha="right", fontsize=11)
        ax.set_ylabel(
            "Percentage Change from Baseline (%)", fontsize=14, fontweight="bold"
        )
        ax.set_xlabel("CT Sample", fontsize=14, fontweight="bold")
        ax.set_title(
            f"{label} Observed as Other Isotype", fontsize=16, fontweight="bold", pad=20
        )
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
        os.path.join(viz_dir, "ig_other_isotype_four_panel_11_samples.png"),
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.savefig(
        os.path.join(viz_dir, "ig_other_isotype_four_panel_11_samples.pdf"),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close()

    # Create horizontal bar chart with absolute values
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    fig.suptitle(
        f"IG Other Isotype Distribution - Absolute Values\n(Baseline: {baseline_sample} highlighted)",
        fontsize=20,
        fontweight="bold",
        y=0.98,
    )

    # Plot each metric as horizontal bars
    for idx, (metric, label, color, ax) in enumerate(
        zip(metrics, metric_labels, colors, axes.flatten())
    ):
        # Get values
        values = df[metric].values

        # Create horizontal bars
        bars = ax.barh(desired_order, values, color=color, alpha=0.8)

        # Highlight baseline bar (NW_11_1030CT - index 9)
        bars[9].set_alpha(1.0)
        bars[9].set_edgecolor("black")
        bars[9].set_linewidth(2)

        # Add baseline reference line
        ax.axvline(
            x=values[baseline_index],
            color="gray",
            linestyle="--",
            linewidth=2,
            alpha=0.8,
        )

        # Add value labels on bars
        for j, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(
                width + max(values) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{width:.2f}%",
                ha="left",
                va="center",
                fontsize=9,
                fontweight="bold",
                color=color,
            )

        # Customize subplot
        ax.set_xlabel("Percentage (%)", fontsize=14, fontweight="bold")
        ax.set_ylabel("CT Sample", fontsize=14, fontweight="bold")
        ax.set_title(
            f"{label} Observed as Other Isotype", fontsize=16, fontweight="bold", pad=20
        )
        ax.grid(axis="x", alpha=0.3, linestyle="--")

        # Set x-axis limit
        ax.set_xlim(0, max(values) * 1.3)

        # Add background color
        ax.set_facecolor("#f8f9fa")

    plt.tight_layout()
    plt.subplots_adjust(top=0.93)

    # Save the figure
    plt.savefig(
        os.path.join(viz_dir, "ig_other_isotype_horizontal_bars_11_samples.png"),
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.savefig(
        os.path.join(viz_dir, "ig_other_isotype_horizontal_bars_11_samples.pdf"),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close()

    print(f"  Saved four panel percentage change chart")
    print(f"  Saved horizontal bar chart with absolute values")

    print(f"\n所有图表已保存至: {viz_dir}")


if __name__ == "__main__":
    extract_ig_other_isotype_data()
