# -*- coding: utf-8 -*-
import csv
import os
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 7,
        "font.weight": "bold",
        "axes.labelweight": "bold",
        "axes.linewidth": 0.6,
        "figure.dpi": 120,
        "savefig.dpi": 600,
    }
)


"""
Input directory. The directory should contain files named like:
TRA.csv, TRB.csv, TRD.csv, TRG.csv, IGH.csv, IGK.csv, IGL.csv
"""
file_dir = "/colddata/data_shared260414/To_ZQY/260507_diabetes/Pep_260213/arrage_pep/Pep_shared_cate/Pep_shared"

"""
Seven receptor chains to scan and plot.
"""
chain_order = ["TRA", "TRB"]

"""
Two exact unique categories:
top section    = CT__count unique CDR3
bottom section = T1DM__count unique CDR3
Shared rows such as ('CT__count', 'T1DM__count') are intentionally excluded.
"""
section_categories = [
    # ("CT__count", "CT unique"),
    ("T1DM__count", "T1DM unique"),
]

"""
X-axis labels.
"category" = keep all sample-column positions, but show each continuous category once.
"index"    = use 1, 2, 3...
"""
x_axis_label_mode = "category"

"""
Number of CDR3 rows to plot per section for each chain.
0 = plot all selected rows.
"""
top_n = 20

"""
1 = normalize each CDR3 row to 0-1, matching the reference heatmap style.
0 = plot raw counts.
"""
row_normalize = 1

"""
Only PNG is exported.
"""
export_format = "png"
dpi = 600
output_dir = os.path.join(file_dir, "CT_SRMCY_unique_heatmap_png")


def get_filesdir(input_dir):
    path_list = []

    for chain in chain_order:
        data_path = os.path.join(input_dir, f"{chain}.csv")
        if os.path.exists(data_path):
            path_list.append(data_path)
        else:
            print(f"Missing, skipped: {data_path}")

    return path_list


def to_float(value):
    value = str(value).strip()
    if value == "":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def normalize_rows(records):
    matrix = []
    for record in records:
        values = record["values"]
        vmax = max(values) if values else 0.0
        if vmax <= 0:
            matrix.append([0.0 for _ in values])
        else:
            matrix.append([value / vmax for value in values])
    return matrix


def get_category_records(
    rows, header, category_col, cdr3_col, sample_idx, chain, category
):
    sort_col_name = f"{category.replace('__count', '')}__sum"
    sort_col = header.index(sort_col_name) if sort_col_name in header else None

    records = []
    for row in rows:
        if not row or len(row) <= category_col:
            continue

        row_category = row[category_col].strip()
        if row_category != category:
            continue

        values = [to_float(row[i]) if i < len(row) else 0.0 for i in sample_idx]
        records.append(
            {
                "chain": chain,
                "cdr3": row[cdr3_col].strip(),
                "category": row_category,
                "values": values,
                "sort_value": (
                    to_float(row[sort_col]) if sort_col is not None else sum(values)
                ),
            }
        )

    records.sort(
        key=lambda item: (item["sort_value"], sum(item["values"])), reverse=True
    )
    selected_count = len(records)
    if top_n > 0:
        records = records[:top_n]

    matrix = [record["values"] for record in records]
    if row_normalize:
        matrix = normalize_rows(records)

    return records, matrix, selected_count


def read_heatmap(data_path, chain):
    with Path(data_path).open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))

    if len(rows) < 3:
        raise ValueError(f"Input CSV must contain two header rows: {data_path}")

    header = rows[0]
    group_row = rows[1]
    data_rows = rows[2:]
    sample_idx = [
        i
        for i, group in enumerate(group_row)
        if i > 0 and group.strip() not in {"", "category"}
    ]

    if not sample_idx:
        raise ValueError(
            f"No sample category columns found in second header row: {data_path}"
        )

    cdr3_col = header.index("CDR3(pep)")
    category_col = header.index("category")

    sample_names = []
    for i in sample_idx:
        sample_name = Path(header[i]).stem
        sample_name = sample_name.replace(f"__{chain}", "")
        sample_names.append(sample_name)

    sample_groups = [group_row[i].strip() for i in sample_idx]

    sections = []
    for category, section_title in get_section_categories():
        records, matrix, selected_count = get_category_records(
            data_rows,
            header,
            category_col,
            cdr3_col,
            sample_idx,
            chain,
            category,
        )
        sections.append(
            {
                "category": category,
                "title": section_title,
                "records": records,
                "matrix": matrix,
                "selected_count": selected_count,
            }
        )

    return {
        "chain": chain,
        "sections": sections,
        "sample_names": sample_names,
        "sample_groups": sample_groups,
    }


def get_cmap():
    return LinearSegmentedColormap.from_list(
        "nature_blue_yellow_red",
        ["#235AA6", "#F3E8A3", "#CF2B24"],
    )


def get_section_categories():
    parsed_categories = []
    for item in section_categories:
        if isinstance(item, str):
            parsed_categories.append((item, item))
            continue

        if len(item) == 0:
            continue

        category = item[0]
        section_title = item[1] if len(item) > 1 else item[0]
        parsed_categories.append((category, section_title))

    return parsed_categories


def get_section_title():
    return " / ".join(section_title for _, section_title in get_section_categories())


def get_x_axis_groups(sample_groups):
    groups = []
    start = 0

    for i in range(1, len(sample_groups) + 1):
        if i == len(sample_groups) or sample_groups[i] != sample_groups[start]:
            groups.append(
                {
                    "label": sample_groups[start],
                    "start": start,
                    "end": i - 1,
                    "center": (start + i - 1) / 2,
                }
            )
            start = i

    return groups


def get_x_axis_fontsize():
    return 7.0 if x_axis_label_mode == "category" else 7.0


def apply_x_axis(heatmap_ax, sample_groups, n_cols):
    if x_axis_label_mode == "category":
        groups = get_x_axis_groups(sample_groups)
        labels = [""] * n_cols
        for group in groups:
            label_at = (group["start"] + group["end"]) // 2
            labels[label_at] = group["label"]

        heatmap_ax.set_xticks(range(n_cols))
        heatmap_ax.set_xticklabels(labels, fontsize=get_x_axis_fontsize())
    else:
        heatmap_ax.set_xticks(range(n_cols))
        heatmap_ax.set_xticklabels(range(1, n_cols + 1), fontsize=get_x_axis_fontsize())

    for label in heatmap_ax.get_xticklabels():
        label.set_fontweight("bold")


def get_color_vmax(payloads):
    if row_normalize:
        return 1.0

    vmax = 0.0
    for payload in payloads:
        for section in payload["sections"]:
            for row in section["matrix"]:
                if row:
                    vmax = max(vmax, max(row))

    return vmax if vmax > 0 else 1.0


def get_combined_records(payload):
    records = []
    matrix = []
    separator_rows = []

    for section in payload["sections"]:
        records.extend(section["records"])
        matrix.extend(section["matrix"])
        separator_rows.append(len(records))

    return records, matrix, separator_rows[:-1]


def draw_combined_axes(
    heatmap_ax,
    payload,
    cmap,
    color_vmax,
    label_font_size=5.2,
    show_title=False,
):
    records, matrix, separator_rows = get_combined_records(payload)
    sample_names = payload["sample_names"]
    sample_groups = payload["sample_groups"]
    chain = payload["chain"]
    n_rows = max(len(records), 1)
    n_cols = len(sample_names)

    if records:
        im = heatmap_ax.imshow(
            matrix,
            aspect="equal",
            interpolation="nearest",
            cmap=cmap,
            vmin=0,
            vmax=color_vmax,
        )
    else:
        im = None
        heatmap_ax.imshow(
            [[0.0 for _ in range(n_cols)]],
            aspect="equal",
            interpolation="nearest",
            cmap=cmap,
            vmin=0,
            vmax=color_vmax,
        )

    apply_x_axis(heatmap_ax, sample_groups, n_cols)
    heatmap_ax.set_yticks([])
    heatmap_ax.tick_params(axis="both", length=0)
    heatmap_ax.set_xticks([i - 0.5 for i in range(1, n_cols)], minor=True)
    heatmap_ax.set_yticks([i - 0.5 for i in range(1, n_rows)], minor=True)
    heatmap_ax.grid(which="minor", color="white", linewidth=1.0)
    heatmap_ax.tick_params(which="minor", bottom=False, left=False)
    heatmap_ax.set_xlim(-0.5, n_cols - 0.5)
    heatmap_ax.set_ylim(n_rows - 0.5, -0.5)

    for spine in heatmap_ax.spines.values():
        spine.set_visible(False)

    if show_title:
        heatmap_ax.set_title(
            f"{chain} | {get_section_title()}",
            loc="left",
            fontsize=8,
            fontweight="bold",
            pad=8,
        )

    if records:
        heatmap_ax.set_yticks(range(n_rows))
        heatmap_ax.set_yticklabels(
            [f"{record['chain']}_{record['cdr3']}" for record in records],
            fontsize=label_font_size,
            fontweight="bold",
        )
        heatmap_ax.yaxis.tick_right()
        heatmap_ax.tick_params(axis="y", which="both", length=0, width=0, pad=7)
    else:
        heatmap_ax.set_yticks([0])
        heatmap_ax.set_yticklabels(
            ["No exact CT__count or SRMCY__count rows"],
            fontsize=label_font_size,
            fontweight="bold",
        )
        heatmap_ax.yaxis.tick_right()
        heatmap_ax.tick_params(axis="y", which="both", length=0, width=0, pad=7)

    return im


def plot_chain_heatmap(payload, color_vmax):
    chain = payload["chain"]
    total_plotted = sum(len(section["records"]) for section in payload["sections"])
    if total_plotted == 0:
        return None

    n_cols = len(payload["sample_names"])
    total_rows = max(total_plotted, 1)
    cell_size = 0.115
    label_width = 1.25
    cbar_gap = 0.03
    cbar_width = 0.10
    cbar_height = 0.78
    left_margin = 0.14
    right_margin = 0.12
    bottom_margin = 0.22
    top_margin = 0.34
    heatmap_width = n_cols * cell_size
    heatmap_height = total_rows * cell_size
    fig_width = (
        heatmap_width + label_width + cbar_gap + cbar_width + left_margin + right_margin
    )
    fig_height = heatmap_height + bottom_margin + top_margin
    cmap = get_cmap()

    fig = plt.figure(figsize=(fig_width, fig_height))
    heatmap_ax = fig.add_axes(
        [
            left_margin / fig_width,
            bottom_margin / fig_height,
            heatmap_width / fig_width,
            heatmap_height / fig_height,
        ]
    )
    cbar_ax = fig.add_axes(
        [
            (left_margin + heatmap_width + label_width + cbar_gap) / fig_width,
            (bottom_margin + heatmap_height - min(cbar_height, heatmap_height))
            / fig_height,
            cbar_width / fig_width,
            min(cbar_height, heatmap_height) / fig_height,
        ]
    )
    label_font_size = 5.4 if total_rows <= 50 else 4.4
    im = draw_combined_axes(
        heatmap_ax,
        payload,
        cmap,
        color_vmax,
        label_font_size=label_font_size,
    )

    cbar = fig.colorbar(im, cax=cbar_ax)
    if row_normalize:
        cbar.set_ticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    cbar.ax.tick_params(labelsize=5.8, length=1.8, width=0.6)
    for tick_label in cbar.ax.get_yticklabels():
        tick_label.set_fontweight("bold")
    cbar.outline.set_linewidth(0.6)

    out_path = os.path.join(
        output_dir, f"{chain}_CT_SRMCY_unique_heatmap.{export_format}"
    )
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    return out_path


def plot_summary_heatmap(payloads, color_vmax):
    payloads = [
        payload
        for payload in payloads
        if sum(len(section["records"]) for section in payload["sections"]) > 0
    ]
    if not payloads:
        return None

    reference_groups = payloads[0]["sample_groups"]
    for payload in payloads[1:]:
        if payload["sample_groups"] != reference_groups:
            raise ValueError(
                "ALL heatmap requires the same sample category order in every chain."
            )

    all_section = {
        "category": "ALL",
        "title": "ALL",
        "records": [],
        "matrix": [],
        "selected_count": 0,
    }
    for payload in payloads:
        for section in payload["sections"]:
            all_section["records"].extend(section["records"])
            all_section["matrix"].extend(section["matrix"])
            all_section["selected_count"] += section["selected_count"]

    all_payload = {
        "chain": "ALL",
        "sections": [all_section],
        "sample_names": payloads[0]["sample_names"],
        "sample_groups": payloads[0]["sample_groups"],
    }

    total_rows = max(len(all_section["records"]), 1)
    n_cols = len(all_payload["sample_names"])
    cell_size = 0.105
    label_width = 1.25
    cbar_gap = 0.03
    cbar_width = 0.10
    cbar_height = 0.78
    left_margin = 0.14
    right_margin = 0.12
    bottom_margin = 0.22
    top_margin = 0.34
    heatmap_width = n_cols * cell_size
    heatmap_height = total_rows * cell_size
    fig_width = (
        heatmap_width + label_width + cbar_gap + cbar_width + left_margin + right_margin
    )
    fig_height = heatmap_height + bottom_margin + top_margin
    cmap = get_cmap()

    fig = plt.figure(figsize=(fig_width, fig_height))
    heatmap_ax = fig.add_axes(
        [
            left_margin / fig_width,
            bottom_margin / fig_height,
            heatmap_width / fig_width,
            heatmap_height / fig_height,
        ]
    )
    cbar_ax = fig.add_axes(
        [
            (left_margin + heatmap_width + label_width + cbar_gap) / fig_width,
            (bottom_margin + heatmap_height - min(cbar_height, heatmap_height))
            / fig_height,
            cbar_width / fig_width,
            min(cbar_height, heatmap_height) / fig_height,
        ]
    )
    label_font_size = 4.8 if total_rows <= 80 else 4.0
    im = draw_combined_axes(
        heatmap_ax,
        all_payload,
        cmap,
        color_vmax,
        label_font_size=label_font_size,
    )

    cbar = fig.colorbar(im, cax=cbar_ax)
    if row_normalize:
        cbar.set_ticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    cbar.ax.tick_params(labelsize=5.8, length=1.8, width=0.6)
    for tick_label in cbar.ax.get_yticklabels():
        tick_label.set_fontweight("bold")
    cbar.outline.set_linewidth(0.6)

    out_path = os.path.join(
        output_dir, f"ALL_CT_SRMCY_unique_heatmap_summary.{export_format}"
    )
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    return out_path


def draw(data_path, color_vmax):
    chain = Path(data_path).stem
    payload = read_heatmap(data_path, chain)
    out_path = plot_chain_heatmap(payload, color_vmax)
    counts = ", ".join(
        f"{section['category']}: matched {section['selected_count']}, plotted {len(section['records'])}"
        for section in payload["sections"]
    )
    print(f"{chain}: {counts}, output {out_path}")
    return payload


if not os.path.exists(output_dir):
    os.makedirs(output_dir)


data_paths = get_filesdir(file_dir)
payload_list = []
for path in data_paths:
    print(f"Reading: {path}")
    payload_list.append(read_heatmap(path, Path(path).stem))

vmax = get_color_vmax(payload_list)

for payload in payload_list:
    out = plot_chain_heatmap(payload, vmax)
    counts = ", ".join(
        f"{section['category']}: matched {section['selected_count']}, plotted {len(section['records'])}"
        for section in payload["sections"]
    )
    print(f"{payload['chain']}: {counts}, output {out}")

summary_path = plot_summary_heatmap(payload_list, vmax)
print(f"Summary output: {summary_path}")
print("Done.")
