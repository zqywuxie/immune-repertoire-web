"""
Extract and visualize CT B cell isotype distribution from PDF reports - Final Version
"""

import pdfplumber
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
import re
from pathlib import Path
from matplotlib import rcParams

# 设置中文字体
rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
rcParams["axes.unicode_minus"] = False


def find_pdf_file(sample_name):
    """Find PDF file for a given sample across all CT directories"""

    # Define search directories
    search_dirs = [
        "/workspace/data_shared/To_ZQY/CT/20250627/pdf_reports",
        "/workspace/data_shared/To_ZQY/CT/20250902/pdf_reports",
        "/workspace/data_shared/To_ZQY/CT/fourth-se300/pdf_reports",
        "/workspace/data_shared/To_ZQY/CT/include_mz/pdf_reports",
    ]

    for directory in search_dirs:
        pdf_path = os.path.join(directory, f"{sample_name}.pdf")
        if os.path.exists(pdf_path):
            return pdf_path

    return None


def extract_isotype_data_from_pdf(pdf_path):
    """Extract B cell isotype distribution data from a PDF file"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Search through all pages for the B cell isotype distribution table
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()

                # Look for the section containing B cell isotype distribution
                if (
                    "B cell Isotype Distribution" in text
                    or "Isotype Distribution" in text
                ):
                    # Extract tables from this page
                    tables = page.extract_tables()

                    for table in tables:
                        # Check if this table contains the isotype data
                        if table and len(table) > 0:
                            header_row = table[0] if table else []

                            # Look for isotype columns
                            isotype_cols = []
                            for col in header_row:
                                if col and (
                                    "IgM" in str(col)
                                    or "IgD" in str(col)
                                    or "IgA" in str(col)
                                    or "IgG" in str(col)
                                    or "IgE" in str(col)
                                ):
                                    isotype_cols.append(col)

                            if len(isotype_cols) >= 5:  # Found isotype data
                                # Find the rows with Expression % and Unique CDR3 %
                                expression_row = None
                                cdr3_row = None

                                for row in table[1:]:
                                    if row and len(row) > 0:
                                        row_text = " ".join(
                                            [str(cell) for cell in row if cell]
                                        )
                                        if "Expression" in row_text and "%" in row_text:
                                            expression_row = row
                                        elif (
                                            "Unique" in row_text and "CDR3" in row_text
                                        ):
                                            cdr3_row = row

                                if expression_row and cdr3_row:
                                    # Extract the numeric values
                                    expression_values = []
                                    cdr3_values = []

                                    for cell in expression_row:
                                        if cell and "%" in str(cell):
                                            # Extract percentage value
                                            match = re.search(r"(\d+\.?\d*)", str(cell))
                                            if match:
                                                expression_values.append(
                                                    float(match.group(1))
                                                )

                                    for cell in cdr3_row:
                                        if cell and "%" in str(cell):
                                            # Extract percentage value
                                            match = re.search(r"(\d+\.?\d*)", str(cell))
                                            if match:
                                                cdr3_values.append(
                                                    float(match.group(1))
                                                )

                                    if (
                                        len(expression_values) >= 5
                                        and len(cdr3_values) >= 5
                                    ):
                                        return {
                                            "expression": expression_values[
                                                :6
                                            ],  # Take first 6 values
                                            "unique_cdr3": cdr3_values[:6],
                                        }

            # If not found with exact match, try alternative approach
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()

                for table in tables:
                    if table and len(table) > 2:
                        # Convert table to text for analysis
                        table_text = []
                        for row in table:
                            table_text.append(
                                " ".join([str(cell) for cell in row if cell])
                            )

                        full_text = " ".join(table_text).lower()

                        # Check if this might be the isotype table
                        if (
                            "igm" in full_text
                            or "igd" in full_text
                            or "iga" in full_text
                            or "igg" in full_text
                        ) and "%" in full_text:

                            # Try to extract data based on pattern
                            expression_values = []
                            cdr3_values = []

                            for row_text in table_text:
                                if "expression" in row_text.lower():
                                    # Extract all percentages from this row
                                    percentages = re.findall(r"(\d+\.?\d*)%", row_text)
                                    expression_values = [float(p) for p in percentages]
                                elif (
                                    "unique" in row_text.lower()
                                    and "cdr3" in row_text.lower()
                                ):
                                    # Extract all percentages from this row
                                    percentages = re.findall(r"(\d+\.?\d*)%", row_text)
                                    cdr3_values = [float(p) for p in percentages]

                            if len(expression_values) >= 5 and len(cdr3_values) >= 5:
                                return {
                                    "expression": expression_values[:6],
                                    "unique_cdr3": cdr3_values[:6],
                                }

        return None

    except Exception as e:
        print(f"Error processing {pdf_path}: {str(e)}")
        return None


def create_bcell_visualizations():
    """Extract B cell isotype data and create visualizations with baseline comparison"""

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

    # Isotype order
    isotypes = ["IgM", "IgD", "IgA1/2", "IgG1/2", "IgG3/4", "IgE"]

    # Extract data from all CT samples
    samples_data = {}

    print("Extracting B cell isotype data from PDF files...")
    for sample_name in desired_order:
        pdf_path = find_pdf_file(sample_name)

        if pdf_path:
            print(f"Processing {sample_name} from {pdf_path}...")
            data = extract_isotype_data_from_pdf(pdf_path)

            if data:
                samples_data[sample_name] = data
                print(f"  Successfully extracted data")
                print(f"  Expression: {data['expression']}")
                print(f"  Unique CDR3: {data['unique_cdr3']}")
            else:
                print(f"  Failed to extract data")
        else:
            print(f"  PDF file not found for {sample_name}")

    if not samples_data:
        print("\nNo data could be extracted from the PDF files.")
        return

    print(f"\nSuccessfully extracted data from {len(samples_data)} samples")

    # Create output directory
    output_dir = "/workspace/data_shared/To_ZQY/CT_BCell_Isotype_Final"
    os.makedirs(output_dir, exist_ok=True)

    # Create visualization subdirectory
    viz_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(viz_dir, exist_ok=True)

    # Create visualizations with original style
    create_expression_visualization(samples_data, desired_order, isotypes, viz_dir)

    # Save CSV data
    save_bcell_data(samples_data, isotypes, output_dir)

    print(f"\n任务完成！")
    print("=" * 60)


def create_expression_visualization(samples_data, samples, isotypes, viz_dir):
    """Create expression percentage visualization with original horizontal bar chart style"""

    # Create individual plots for each sample
    for sample_name in samples:
        if sample_name not in samples_data:
            continue

        data = samples_data[sample_name]

        # Create figure with two subplots (horizontal layout)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        fig.suptitle(
            f"B Cell Isotype Distribution ({sample_name})",
            fontsize=18,
            fontweight="bold",
            y=0.95,
        )

        # Sort data by percentage for better visualization
        # For Expression %
        expr_sorted = sorted(
            zip(isotypes, data["expression"]), key=lambda x: x[1], reverse=True
        )
        expr_isotypes, expr_values = zip(*expr_sorted)

        # For Unique CDR3 %
        cdr3_sorted = sorted(
            zip(isotypes, data["unique_cdr3"]), key=lambda x: x[1], reverse=True
        )
        cdr3_isotypes, cdr3_values = zip(*cdr3_sorted)

        # Create horizontal bars for Expression %
        colors1 = ["#2E86AB", "#457B9D", "#5DADE2", "#85C1E9", "#AED6F1", "#D6EAF8"]
        bars1 = ax1.barh(
            range(len(expr_isotypes)),
            expr_values,
            color=colors1[: len(expr_isotypes)],
            alpha=0.8,
        )

        # Customize Expression subplot
        ax1.set_xlabel("Percentage (%)", fontsize=14, fontweight="bold")
        ax1.set_title("Expression %", fontsize=16, fontweight="bold", pad=20)
        ax1.set_yticks(range(len(expr_isotypes)))
        ax1.set_yticklabels(expr_isotypes, fontsize=12)

        # Add grid
        ax1.grid(axis="x", alpha=0.3, linestyle="--")

        # Add value labels
        for i, (bar, value) in enumerate(zip(bars1, expr_values)):
            ax1.text(
                value + max(expr_values) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{value:.2f}%",
                ha="left",
                va="center",
                fontsize=11,
                fontweight="bold",
            )

        # Set x-axis limit
        ax1.set_xlim(0, max(expr_values) * 1.15)

        # Create horizontal bars for Unique CDR3 %
        colors2 = ["#A23B72", "#C06C84", "#F67280", "#F8B195", "#F6B352", "#FFA07A"]
        bars2 = ax2.barh(
            range(len(cdr3_isotypes)),
            cdr3_values,
            color=colors2[: len(cdr3_isotypes)],
            alpha=0.8,
        )

        # Customize Unique CDR3 subplot
        ax2.set_xlabel("Percentage (%)", fontsize=14, fontweight="bold")
        ax2.set_title("Unique CDR3 %", fontsize=16, fontweight="bold", pad=20)
        ax2.set_yticks(range(len(cdr3_isotypes)))
        ax2.set_yticklabels(cdr3_isotypes, fontsize=12)

        # Add grid
        ax2.grid(axis="x", alpha=0.3, linestyle="--")

        # Add value labels
        for i, (bar, value) in enumerate(zip(bars2, cdr3_values)):
            ax2.text(
                value + max(cdr3_values) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{value:.2f}%",
                ha="left",
                va="center",
                fontsize=11,
                fontweight="bold",
            )

        # Set x-axis limit
        ax2.set_xlim(0, max(cdr3_values) * 1.15)

        # Add background color
        ax1.set_facecolor("#f8f9fa")
        ax2.set_facecolor("#f8f9fa")

        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(top=0.88)

        # Save individual plots
        plt.savefig(
            os.path.join(viz_dir, f"{sample_name}_isotype_distribution.png"),
            dpi=300,
            bbox_inches="tight",
            facecolor="white",
        )
        plt.savefig(
            os.path.join(viz_dir, f"{sample_name}_isotype_distribution.pdf"),
            bbox_inches="tight",
            facecolor="white",
        )
        plt.close()

    print(f"  Saved B cell isotype distribution charts (original style)")


def create_cdr3_visualization(samples_data, samples, isotypes, viz_dir):
    """Create unique CDR3 percentage visualization with baseline comparison"""

    # Use NW_11_1030CT as baseline (index 9 in 11-sample list)
    baseline_sample = "NW_11_1030CT"
    baseline_index = 9

    # Create figure with 2x3 subplots
    fig, axes = plt.subplots(2, 3, figsize=(24, 16))
    fig.suptitle(
        f"B Cell Unique CDR3 - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
        fontsize=20,
        fontweight="bold",
        y=0.98,
    )

    # Flatten axes for easier iteration
    axes = axes.flatten()

    # Define colors for each isotype
    colors = {
        "IgM": "#1f77b4",
        "IgD": "#ff7f0e",
        "IgA1/2": "#2ca02c",
        "IgG1/2": "#d62728",
        "IgG3/4": "#9467bd",
        "IgE": "#8c564b",
    }

    x_pos = np.arange(len(samples))
    bar_width = 0.6

    # Plot each isotype
    for idx, (isotype, ax) in enumerate(zip(isotypes, axes)):
        # Get CDR3 values for all samples
        values = []
        for sample in samples:
            if sample in samples_data:
                # Find the index for this isotype
                iso_idx = isotypes.index(isotype)
                if iso_idx < len(samples_data[sample]["unique_cdr3"]):
                    values.append(samples_data[sample]["unique_cdr3"][iso_idx])
                else:
                    values.append(0)
            else:
                values.append(0)

        values = np.array(values)

        # Get baseline value
        baseline_value = values[baseline_index]

        # Calculate percentage changes
        pct_change = (values - baseline_value) / baseline_value * 100

        # Create vertical bars
        bars = ax.bar(x_pos, pct_change, bar_width, color=colors[isotype], alpha=0.8)

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
        ax.set_title(f"{isotype} Unique CDR3", fontsize=16, fontweight="bold", pad=20)
        ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
        ax.grid(axis="y", alpha=0.3, linestyle="--")

        # Set y-axis limits
        ymin = min(pct_change) * 1.1 if min(pct_change) < 0 else -5
        ymax = max(pct_change) * 1.1 if max(pct_change) > 0 else 5
        ax.set_ylim(ymin, ymax)

        # Add background color
        ax.set_facecolor("#f8f9fa")

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    # Save the figure
    plt.savefig(
        os.path.join(viz_dir, "bcell_cdr3_percentage_change_11_samples.png"),
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.savefig(
        os.path.join(viz_dir, "bcell_cdr3_percentage_change_11_samples.pdf"),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close()

    print(f"  Saved B cell CDR3 percentage change chart")


def save_bcell_data(samples_data, isotypes, output_dir):
    """Save B cell isotype data to CSV"""

    # Prepare data for CSV
    bcell_data = []

    for sample_name in samples_data:
        data = samples_data[sample_name]
        row = {"Sample": sample_name}

        # Add expression and CDR3 data for each isotype
        for i, isotype in enumerate(isotypes):
            if i < len(data["expression"]):
                row[f"{isotype}_Expression"] = f"{data['expression'][i]:.2f}%"
            else:
                row[f"{isotype}_Expression"] = "0.00%"

            if i < len(data["unique_cdr3"]):
                row[f"{isotype}_Unique_CDR3"] = f"{data['unique_cdr3'][i]:.2f}%"
            else:
                row[f"{isotype}_Unique_CDR3"] = "0.00%"

        bcell_data.append(row)

    # Create DataFrame and save
    bcell_df = pd.DataFrame(bcell_data)
    csv_file = os.path.join(output_dir, "ct_samples_bcell_isotype_data.csv")
    bcell_df.to_csv(csv_file, index=False)
    print(f"\nB cell isotype数据已保存至: {csv_file}")

    # Print data summary
    print("\nCT样本B cell isotype数据：")
    print("=" * 140)
    print(bcell_df.to_string(index=False))


if __name__ == "__main__":
    create_bcell_visualizations()
