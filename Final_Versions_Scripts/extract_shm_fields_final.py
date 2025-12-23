"""
Extract and visualize CT SHM (Somatic Hypermutation) data from Excel - Final Version
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


def extract_shm_data_from_excel():
    """Extract SHM data from Excel file"""

    # Read the Excel file
    excel_file = "/workspace/data_shared/To_ZQY/CT/CT数据汇总.xlsx"
    df = pd.read_excel(excel_file)

    # Filter for CT samples
    ct_samples = df[df["Sample"].str.contains(r"NW_11_\d{4}CT$", regex=True, na=False)]

    return ct_samples


def create_shm_visualizations():
    """Create SHM visualizations with baseline comparison"""

    # Extract data
    ct_samples = extract_shm_data_from_excel()

    if ct_samples is None or len(ct_samples) == 0:
        print("No CT samples found in the data.")
        return

    print(f"Found {len(ct_samples)} CT samples")

    # Define the desired sample order
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

    # Create output directory
    output_dir = "/workspace/data_shared/To_ZQY/CT_SHM_Final"
    os.makedirs(output_dir, exist_ok=True)

    # Create visualization subdirectory
    viz_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(viz_dir, exist_ok=True)

    # Define SHM field pairs for visualization
    ig_shm_pairs = [
        ("IGHA_SHM0", "IGHA_SHM1", "IgA"),
        ("IGHG12_SHM0", "IGHG12_SHM1", "IgG1/2"),
        ("IGHG34_SHM0", "IGHG34_SHM1", "IgG3/4"),
        ("IGHM_IGHD_SHM0", "IGHM_IGHD_SHM1", "IgM/IgD"),
    ]

    # Create IG SHM visualization
    create_ig_shm_figure(ct_samples, desired_order, ig_shm_pairs, viz_dir)

    # Create overall IGH SHM visualization
    create_igh_shm_figure(ct_samples, desired_order, viz_dir)

    # Save CSV data
    save_shm_data(ct_samples, ig_shm_pairs, output_dir)

    print(f"\n任务完成！")
    print("=" * 60)


def create_ig_shm_figure(df, samples, shm_pairs, viz_dir):
    """Create IG SHM visualization with 2x2 subplots"""

    # Use NW_11_1030CT as baseline (index 9 in 11-sample list)
    baseline_sample = "NW_11_1030CT"
    baseline_index = 9

    # Create figure with 2x2 subplots
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    fig.suptitle(
        f"IG Somatic Hypermutation - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
        fontsize=20,
        fontweight="bold",
        y=0.98,
    )

    # Flatten axes for easier iteration
    axes = axes.flatten()

    # Define colors
    colors = {
        "IgA": "#1f77b4",
        "IgG1/2": "#ff7f0e",
        "IgG3/4": "#2ca02c",
        "IgM/IgD": "#d62728",
    }

    x_pos = np.arange(len(samples))
    bar_width = 0.35

    # Plot each isotype
    for idx, ((shm0, shm1, isotype), ax) in enumerate(zip(shm_pairs, axes)):
        # Get values for SHM0 and SHM1
        values0 = df[shm0].values
        values1 = df[shm1].values

        # Get baseline values
        baseline0 = values0[baseline_index]
        baseline1 = values1[baseline_index]

        # Calculate percentage changes
        pct_change0 = (values0 - baseline0) / baseline0 * 100
        pct_change1 = (values1 - baseline1) / baseline1 * 100

        # Create vertical bars
        bars0 = ax.bar(
            x_pos - bar_width / 2,
            pct_change0,
            bar_width,
            label=f"{isotype} SHM0",
            color=colors[isotype],
            alpha=0.8,
        )
        bars1 = ax.bar(
            x_pos + bar_width / 2,
            pct_change1,
            bar_width,
            label=f"{isotype} SHM1",
            color=colors[isotype],
            alpha=0.6,
            hatch="//",
        )

        # Highlight baseline bars
        bars0[baseline_index].set_edgecolor("black")
        bars0[baseline_index].set_linewidth(2)
        bars0[baseline_index].set_alpha(1.0)
        bars1[baseline_index].set_edgecolor("black")
        bars1[baseline_index].set_linewidth(2)
        bars1[baseline_index].set_alpha(1.0)

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
        all_values = list(pct_change0) + list(pct_change1)
        max_val = max(abs(v) for v in all_values if not np.isnan(v))

        for j, (bar0, bar1) in enumerate(zip(bars0, bars1)):
            height0 = bar0.get_height()
            height1 = bar1.get_height()

            # SHM0 labels
            if j == baseline_index:
                ax.text(
                    bar0.get_x() + bar0.get_width() / 2,
                    height0 + max_val * 0.02,
                    "Baseline",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color="red",
                )
            elif height0 > 0:
                ax.text(
                    bar0.get_x() + bar0.get_width() / 2,
                    height0 + max_val * 0.02,
                    f"+{height0:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    fontweight="bold",
                )
            else:
                ax.text(
                    bar0.get_x() + bar0.get_width() / 2,
                    height0 - max_val * 0.02,
                    f"{height0:.1f}%",
                    ha="center",
                    va="top",
                    fontsize=8,
                    fontweight="bold",
                )

            # SHM1 labels
            if height1 > 0:
                ax.text(
                    bar1.get_x() + bar1.get_width() / 2,
                    height1 + max_val * 0.02,
                    f"+{height1:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    fontweight="bold",
                )
            else:
                ax.text(
                    bar1.get_x() + bar1.get_width() / 2,
                    height1 - max_val * 0.02,
                    f"{height1:.1f}%",
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
        ax.set_title(f"{isotype} SHM Levels", fontsize=16, fontweight="bold", pad=20)
        ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
        ax.grid(axis="y", alpha=0.3, linestyle="--")

        # Set y-axis limits
        ymin = min(min(pct_change0), min(pct_change1)) * 1.1
        ymax = max(max(pct_change0), max(pct_change1)) * 1.1
        ax.set_ylim(ymin, ymax)

        # Add background color
        ax.set_facecolor("#f8f9fa")

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    # Save the figure
    plt.savefig(
        os.path.join(viz_dir, "ig_shm_percentage_change_11_samples.png"),
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.savefig(
        os.path.join(viz_dir, "ig_shm_percentage_change_11_samples.pdf"),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close()

    print(f"  Saved IG SHM percentage change chart")


def create_igh_shm_figure(df, samples, viz_dir):
    """Create overall IGH SHM visualization"""

    # Use NW_11_1030CT as baseline (index 9 in 11-sample list)
    baseline_sample = "NW_11_1030CT"
    baseline_index = 9

    # Create figure
    fig, ax = plt.subplots(figsize=(16, 8))

    # Get values for IGH SHM0 and SHM1
    values0 = df["IGH_SHM0"].values
    values1 = df["IGH_SHM1"].values

    # Get baseline values
    baseline0 = values0[baseline_index]
    baseline1 = values1[baseline_index]

    # Calculate percentage changes
    pct_change0 = (values0 - baseline0) / baseline0 * 100
    pct_change1 = (values1 - baseline1) / baseline1 * 100

    # Create vertical bars
    x_pos = np.arange(len(samples))
    bar_width = 0.35

    bars0 = ax.bar(
        x_pos - bar_width / 2,
        pct_change0,
        bar_width,
        label="IGH SHM0",
        color="#9467bd",
        alpha=0.8,
    )
    bars1 = ax.bar(
        x_pos + bar_width / 2,
        pct_change1,
        bar_width,
        label="IGH SHM1",
        color="#9467bd",
        alpha=0.6,
        hatch="//",
    )

    # Highlight baseline bars
    bars0[baseline_index].set_edgecolor("black")
    bars0[baseline_index].set_linewidth(2)
    bars0[baseline_index].set_alpha(1.0)
    bars1[baseline_index].set_edgecolor("black")
    bars1[baseline_index].set_linewidth(2)
    bars1[baseline_index].set_alpha(1.0)

    # Add baseline reference line at 0%
    ax.axhline(
        y=0, color="gray", linestyle="-", linewidth=2, alpha=0.8, label="Baseline (0%)"
    )

    # Add value labels on bars
    all_values = list(pct_change0) + list(pct_change1)
    max_val = max(abs(v) for v in all_values if not np.isnan(v))

    for j, (bar0, bar1) in enumerate(zip(bars0, bars1)):
        height0 = bar0.get_height()
        height1 = bar1.get_height()

        # SHM0 labels
        if j == baseline_index:
            ax.text(
                bar0.get_x() + bar0.get_width() / 2,
                height0 + max_val * 0.02,
                "Baseline",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
                color="red",
            )
        elif height0 > 0:
            ax.text(
                bar0.get_x() + bar0.get_width() / 2,
                height0 + max_val * 0.02,
                f"+{height0:.1f}%",
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
            )
        else:
            ax.text(
                bar0.get_x() + bar0.get_width() / 2,
                height0 - max_val * 0.02,
                f"{height0:.1f}%",
                ha="center",
                va="top",
                fontsize=8,
                fontweight="bold",
            )

        # SHM1 labels
        if height1 > 0:
            ax.text(
                bar1.get_x() + bar1.get_width() / 2,
                height1 + max_val * 0.02,
                f"+{height1:.1f}%",
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
            )
        else:
            ax.text(
                bar1.get_x() + bar1.get_width() / 2,
                height1 - max_val * 0.02,
                f"{height1:.1f}%",
                ha="center",
                va="top",
                fontsize=8,
                fontweight="bold",
            )

    # Customize the plot
    ax.set_xticks(x_pos)
    ax.set_xticklabels(samples, rotation=45, ha="right", fontsize=12)
    ax.set_ylabel("Percentage Change from Baseline (%)", fontsize=14, fontweight="bold")
    ax.set_xlabel("CT Sample", fontsize=14, fontweight="bold")
    ax.set_title(
        f"Overall IGH SHM Levels - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
        fontsize=16,
        fontweight="bold",
        pad=20,
    )
    ax.legend(fontsize=11, frameon=True, fancybox=True, shadow=True)
    ax.grid(axis="y", alpha=0.3, linestyle="--")

    # Set y-axis limits
    ymin = min(min(pct_change0), min(pct_change1)) * 1.1
    ymax = max(max(pct_change0), max(pct_change1)) * 1.1
    ax.set_ylim(ymin, ymax)

    # Add background color
    ax.set_facecolor("#f8f9fa")

    plt.tight_layout()

    # Save the figure
    plt.savefig(
        os.path.join(viz_dir, "igh_shm_percentage_change_11_samples.png"),
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.savefig(
        os.path.join(viz_dir, "igh_shm_percentage_change_11_samples.pdf"),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close()

    print(f"  Saved IGH SHM percentage change chart")


def save_shm_data(df, shm_pairs, output_dir):
    """Save SHM data to CSV with specified field order"""

    # Prepare data for CSV with specified order
    shm_data = []

    for _, row in df.iterrows():
        sample = row["Sample"]
        shm_row = {"Sample": sample}

        # Add fields in the specified order
        shm_row["IGHA_SHM0"] = f"{row['IGHA_SHM0']:.4f}"
        shm_row["IGHG12_SHM0"] = f"{row['IGHG12_SHM0']:.4f}"
        shm_row["IGHG34_SHM0"] = f"{row['IGHG34_SHM0']:.4f}"
        shm_row["IGHM_IGHD_SHM0"] = f"{row['IGHM_IGHD_SHM0']:.4f}"
        shm_row["IGHA_SHM1"] = f"{row['IGHA_SHM1']:.4f}"
        shm_row["IGHG12_SHM1"] = f"{row['IGHG12_SHM1']:.4f}"
        shm_row["IGHG34_SHM1"] = f"{row['IGHG34_SHM1']:.4f}"
        shm_row["IGHM_IGHD_SHM1"] = f"{row['IGHM_IGHD_SHM1']:.4f}"
        shm_row["IGH_SHM0"] = f"{row['IGH_SHM0']:.4f}"
        shm_row["IGH_SHM1"] = f"{row['IGH_SHM1']:.4f}"

        shm_data.append(shm_row)

    # Create DataFrame and save
    shm_df = pd.DataFrame(shm_data)
    csv_file = os.path.join(output_dir, "ct_samples_shm_data.csv")
    shm_df.to_csv(csv_file, index=False)
    print(f"\nSHM数据已保存至: {csv_file}")

    # Print data summary
    print("\nCT样本SHM数据：")
    print("=" * 140)
    print(shm_df.to_string(index=False))


if __name__ == "__main__":
    create_shm_visualizations()
