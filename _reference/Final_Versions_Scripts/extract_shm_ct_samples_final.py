"""
Extract SHM (Somatic Hypermutation) fields for CT samples from Excel - Final Version
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
    """Extract SHM fields for CT samples from Excel file"""

    # Create output directory
    output_dir = Path("/workspace/data_shared/To_ZQY/ct_shm_analysis_final")
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

    # Define SHM fields
    shm_fields = [
        "IGHA_SHM0",
        "IGHG12_SHM0",
        "IGHG34_SHM0",
        "IGHM_IGHD_SHM0",
        "IGHA_SHM1",
        "IGHG12_SHM1",
        "IGHG34_SHM1",
        "IGHM_IGHD_SHM1",
        "IGH_SHM0",
        "IGH_SHM1",
    ]

    # Check available fields
    available_fields = [field for field in shm_fields if field in ct_samples.columns]

    if not available_fields:
        print("No SHM fields found in the data.")
        return

    # Extract data
    output_data = ct_samples[["Sample"] + available_fields].copy()

    # Save to CSV
    csv_file = output_dir / "ct_samples_shm_data.csv"
    output_data.to_csv(csv_file, index=False)
    print(f"\nSHM data saved to: {csv_file}")

    # Create visualizations
    create_shm_visualizations(output_data, output_dir)

    print(f"\nTask complete!")
    print("=" * 60)


def create_shm_visualizations(df, output_dir):
    """Create SHM visualizations with baseline comparison"""

    # Create visualization directory
    viz_dir = output_dir / "visualizations"
    viz_dir.mkdir(exist_ok=True)

    # Define isotype pairs
    isotype_pairs = [
        ("IGHA_SHM0", "IGHA_SHM1", "IgA"),
        ("IGHG12_SHM0", "IGHG12_SHM1", "IgG1/2"),
        ("IGHG34_SHM0", "IGHG34_SHM1", "IgG3/4"),
        ("IGHM_IGHD_SHM0", "IGHM_IGHD_SHM1", "IgM/IgD"),
    ]

    # Create four separate plots with baseline
    create_four_panel_chart_with_baseline(df, isotype_pairs, viz_dir)

    print(f"\nAll charts saved in '{viz_dir}' directory.")


def create_four_panel_chart_with_baseline(df, isotype_pairs, viz_dir):
    """Create four separate plots for each isotype with baseline reference"""

    # Use NW_11_1030CT as baseline (index 9 in 11-sample list)
    baseline_sample = "NW_11_1030CT"
    baseline_index = 9  # Index of NW_11_1030CT in the desired_order list
    baseline_row = df.iloc[baseline_index]

    # Create figure with 2x2 subplots
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    fig.suptitle(
        f"Somatic Hypermutation (SHM) Levels by Isotype\n(Baseline: {baseline_sample})",
        fontsize=20,
        fontweight="bold",
        y=0.98,
    )

    # Define colors (blue and orange)
    colors = ["#1f77b4", "#ff7f0e"]
    x_pos = np.arange(len(df))
    bar_width = 0.35

    # Plot each isotype in a separate subplot
    for idx, (shm0, shm1, isotype, ax) in enumerate(
        zip(
            [pair[0] for pair in isotype_pairs],
            [pair[1] for pair in isotype_pairs],
            [pair[2] for pair in isotype_pairs],
            axes.flatten(),
        )
    ):
        # Get values and calculate percentage changes
        shm0_values = df[shm0].values
        shm1_values = df[shm1].values
        baseline_shm0 = baseline_row[shm0]
        baseline_shm1 = baseline_row[shm1]

        shm0_pct_change = (shm0_values - baseline_shm0) / baseline_shm0 * 100
        shm1_pct_change = (shm1_values - baseline_shm1) / baseline_shm1 * 100

        # Create vertical bars
        bars0 = ax.bar(
            x_pos - bar_width / 2,
            shm0_pct_change,
            bar_width,
            label="SHM0 (Unmutated)",
            color=colors[0],
            alpha=0.8,
        )
        bars1 = ax.bar(
            x_pos + bar_width / 2,
            shm1_pct_change,
            bar_width,
            label="SHM1 (Mutated)",
            color=colors[1],
            alpha=0.8,
        )

        # Highlight baseline bars (NW_11_1030CT - index 9)
        bars0[9].set_alpha(1.0)  # Make baseline bar fully opaque
        bars0[9].set_edgecolor("black")
        bars0[9].set_linewidth(2)
        bars1[9].set_alpha(1.0)  # Make baseline bar fully opaque
        bars1[9].set_edgecolor("black")
        bars1[9].set_linewidth(2)

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
        for j, (bar0, bar1) in enumerate(zip(bars0, bars1)):
            # SHM0 labels
            height0 = bar0.get_height()
            if height0 >= 0:
                ax.text(
                    bar0.get_x() + bar0.get_width() / 2,
                    height0 + max(shm0_pct_change) * 0.02,
                    f"+{height0:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color=colors[0],
                )
            else:
                ax.text(
                    bar0.get_x() + bar0.get_width() / 2,
                    height0 - max(shm0_pct_change) * 0.02,
                    f"{height0:.1f}%",
                    ha="center",
                    va="top",
                    fontsize=9,
                    fontweight="bold",
                    color=colors[0],
                )

            # SHM1 labels
            height1 = bar1.get_height()
            if height1 >= 0:
                ax.text(
                    bar1.get_x() + bar1.get_width() / 2,
                    height1 + max(shm1_pct_change) * 0.02,
                    f"+{height1:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color=colors[1],
                )
            else:
                ax.text(
                    bar1.get_x() + bar1.get_width() / 2,
                    height1 - max(shm1_pct_change) * 0.02,
                    f"{height1:.1f}%",
                    ha="center",
                    va="top",
                    fontsize=9,
                    fontweight="bold",
                    color=colors[1],
                )

        # Customize subplot
        ax.set_xticks(x_pos)
        ax.set_xticklabels(df["Sample"].tolist(), rotation=45, ha="right", fontsize=11)
        ax.set_ylabel(
            "Percentage Change from Baseline (%)", fontsize=14, fontweight="bold"
        )
        ax.set_xlabel("CT Sample", fontsize=14, fontweight="bold")
        ax.set_title(f"{isotype} Isotype", fontsize=16, fontweight="bold", pad=20)
        ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
        ax.grid(axis="y", alpha=0.3, linestyle="--")

        # Set y-axis limits for percentage values
        all_pct_changes = np.concatenate([shm0_pct_change, shm1_pct_change])
        ymin = min(all_pct_changes) * 1.1 if min(all_pct_changes) < 0 else -5
        ymax = max(all_pct_changes) * 1.1 if max(all_pct_changes) > 0 else 5
        ax.set_ylim(ymin, ymax)

        # Add background color
        ax.set_facecolor("#f8f9fa")

    plt.tight_layout()
    plt.subplots_adjust(top=0.93)

    # Save the figure
    plt.savefig(
        viz_dir / "shm_four_panel_with_baseline_11_samples.png",
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.savefig(
        viz_dir / "shm_four_panel_with_baseline_11_samples.pdf",
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close()

    print(f"  Saved four panel chart with baseline ({baseline_sample})")


if __name__ == "__main__":
    extract_ct_shm_classification()
