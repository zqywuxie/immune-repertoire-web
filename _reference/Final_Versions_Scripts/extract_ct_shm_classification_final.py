"""
Extract SHM (Somatic Hypermutation) classification fields for CT samples from Excel - Final Version
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
from pathlib import Path

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


def extract_ct_shm_classification():
    """Extract SHM classification fields for CT samples from Excel file"""

    # Create output directory
    output_dir = Path("/workspace/data_shared/To_ZQY/CT_SHM_Classification_Final")
    output_dir.mkdir(exist_ok=True)

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

    # Define SHM classification fields
    shm_class_fields = [
        "class_switched_percent_by_reads",
        "naive_mutated_percent_by_reads",
        "naive_unmutated_percent_by_reads",
        "IGHM_IGHD_mutated_by_reads",
        "class_switched_percent_by_clone",
        "naive_mutated_percent_by_clone",
        "naive_unmutated_percent_by_clone",
        "IGHM_IGHD_mutated_by_clone",
    ]

    # Check available fields
    available_fields = [
        field for field in shm_class_fields if field in ct_samples.columns
    ]

    if not available_fields:
        print("No SHM classification fields found in the data.")
        return

    # Extract data
    output_data = ct_samples[["Sample"] + available_fields].copy()

    # Display the data
    print("\nCT样本SHM分类数据：")
    print("=" * 100)
    for idx, row in output_data.iterrows():
        print(f"\n样本: {row['Sample']}")
        print("-" * 80)
        for field in available_fields:
            value = row[field]
            field_name = (
                field.replace("_percent_by_reads", " (% Reads)")
                .replace("_percent_by_clone", " (% Clones)")
                .replace("_mutated_by_reads", " (% Reads)")
                .replace("_mutated_by_clone", " (% Clones)")
            )
            if "class_switched" in field:
                field_name = field_name.replace("class_switched", "Class-Switched")
            elif "naive_mutated" in field:
                field_name = field_name.replace("naive_mutated", "Naive-Mutated")
            elif "naive_unmutated" in field:
                field_name = field_name.replace("naive_unmutated", "Naive-Unmutated")
            elif "IGHM_IGHD_mutated" in field:
                field_name = field_name.replace(
                    "IGHM_IGHD_mutated", "IGHM/IGHD-Mutated"
                )
            print(f"  {field_name:<30}: {value:.2f}%")

    # Save to CSV
    csv_file = output_dir / "CT_samples_shm_classification.csv"
    output_data.to_csv(csv_file, index=False)
    print(f"\n数据已保存至: {csv_file}")

    # Create optimized four-panel visualizations
    create_optimized_four_panel_charts(output_data, output_dir)

    print(f"\n任务完成！")
    print("=" * 60)


def create_optimized_four_panel_charts(data, output_dir):
    """Create optimized four-panel charts with baseline comparison"""

    # Create visualization directory
    viz_dir = output_dir / "visualizations"
    viz_dir.mkdir(exist_ok=True)

    # Prepare data for plotting
    reads_fields = [f for f in data.columns if "reads" in f and f != "Sample"]
    clones_fields = [f for f in data.columns if "clone" in f and f != "Sample"]

    # Create shorter labels for display
    label_map = {
        "class_switched_percent_by_reads": "Class-Switched",
        "naive_mutated_percent_by_reads": "Naive-Mutated",
        "naive_unmutated_percent_by_reads": "Naive-Unmutated",
        "IGHM_IGHD_mutated_by_reads": "IGHM/IGHD-Mutated",
        "class_switched_percent_by_clone": "Class-Switched",
        "naive_mutated_percent_by_clone": "Naive-Mutated",
        "naive_unmutated_percent_by_clone": "Naive-Unmutated",
        "IGHM_IGHD_mutated_by_clone": "IGHM/IGHD-Mutated",
    }

    # Define colors (blue and orange)
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

    # Create two figures: one for reads, one for clones
    for fields, data_type, title_suffix in [
        (reads_fields, "by_reads", "By Reads"),
        (clones_fields, "by_clones", "By Clones"),
    ]:
        # Create figure with 2x2 subplots
        fig, axes = plt.subplots(2, 2, figsize=(20, 16))
        fig.suptitle(
            f"SHM Classification {title_suffix} - Percentage Change from Baseline\n(Baseline: NW_11_1030CT)",
            fontsize=20,
            fontweight="bold",
            y=0.98,
        )

        x_pos = np.arange(len(data))
        bar_width = 0.35

        # Use NW_11_1030CT as baseline (index 9 in 11-sample list)
        baseline_sample = "NW_11_1030CT"
        baseline_index = 9
        baseline_row = data.iloc[baseline_index]

        # Plot each field in a separate subplot
        for idx, (field, ax) in enumerate(zip(fields, axes.flatten())):
            # Get values and calculate percentage changes
            values = data[field].values
            baseline_value = baseline_row[field]
            pct_change = (values - baseline_value) / baseline_value * 100

            # Create vertical bars
            bars = ax.bar(
                x_pos,
                pct_change,
                bar_width,
                label=label_map[field],
                color=colors[idx],
                alpha=0.8,
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
            ax.set_xticklabels(
                data["Sample"].tolist(), rotation=45, ha="right", fontsize=11
            )
            ax.set_ylabel(
                "Percentage Change from Baseline (%)", fontsize=14, fontweight="bold"
            )
            ax.set_xlabel("CT Sample", fontsize=14, fontweight="bold")
            ax.set_title(f"{label_map[field]}", fontsize=16, fontweight="bold", pad=20)
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
        filename = f"shm_classification_{data_type}_four_panel_11_samples.png"
        plt.savefig(viz_dir / filename, dpi=300, bbox_inches="tight", facecolor="white")
        plt.savefig(
            viz_dir / filename.replace(".png", ".pdf"),
            bbox_inches="tight",
            facecolor="white",
        )
        plt.close()

        print(f"  Saved {title_suffix} four panel chart")

    print(f"\n所有图表已保存至: {viz_dir}")


if __name__ == "__main__":
    extract_ct_shm_classification()
