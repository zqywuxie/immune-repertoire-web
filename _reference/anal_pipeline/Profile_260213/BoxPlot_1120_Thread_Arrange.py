# -*- coding: utf-8 -*-
import pandas as pd
from scipy.stats import mannwhitneyu
from itertools import combinations
import seaborn as sns
import os
import math
import re
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.ticker as mticker

axis_label_font_size = 10.5
tick_font_size = 8
y_label_gutter_width = 0.60
y_label_x_position = -0.28
y_label_tick_gap_px = 8
save_pad_inches = 0.06
save_bbox_inches = "tight"
compact_y_tick_threshold_low = 0.01
compact_y_tick_threshold_high = 10000

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": axis_label_font_size,
        "font.weight": "semibold",
        "axes.labelweight": "semibold",
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.edgecolor": "#2B2B2B",
        "xtick.color": "#2B2B2B",
        "ytick.color": "#2B2B2B",
        "axes.linewidth": 0.8,
        "legend.frameon": False,
        "figure.dpi": 120,
        "savefig.dpi": 600,
    }
)

file_dir = "/data/scAnalyis/260508/anal/Datapoints/current/Datapoint.csv"

"""
if filename_or_file = 1, input is a dirname
if filename_or_file = 0, input will be a filename
"""
filename_or_file = 0

"""
绘图阈值
1 = 所有参数全部绘图
0.05 = 仅显著参数绘图
"""
plot_threshold_pvalue = 1

"""
显著性 txt 输出阈值
"""
sig_threshold_pvalue = 0.05

"""
透明背景开关
1 = 透明背景
0 = 白色背景
"""
transparent_background = 0

"""
期刊输出格式
"""
export_formats = ["png"]

"""
输出目录
"""
output_dir = "boxplot"


def make_output_path(stem, section, subdir="", *parts):
    """Build one CSV-rooted output path.

    Layout:
        output_dir/<csv_stem>/figure/...
        output_dir/<csv_stem>/file/...
    """
    components = [output_dir, stem, section]
    if subdir:
        components.append(subdir)
    components.extend(part for part in parts if part)
    return os.path.join(*components)


def split_output_context(filename):
    parts = os.path.normpath(filename).split(os.sep)
    stem = parts[0]
    subdir = os.path.join(*parts[1:]) if len(parts) > 1 else ""
    return stem, subdir


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


"""
跨链汇总图：把同一指标在当前数据实际包含的链间合并展示。
参数名支持 TRA_ratio_VDJdb 或 ratio_VDJdb_TRA；
也就是支持 链名_指标名 和 指标名_链名 两种格式。
下面列表仅用于常见链的优先排序，不要求每个指标都包含这些链。
"""
summary_chain_order = ["TRA", "TRB", "TRD", "TRG", "IGH", "IGK", "IGL"]
summary_fig_width = 4.2
summary_fig_height = 2.6
summary_bar_width = 0.72
summary_bar_edge_width = 0.6
summary_errorbar_line_width = 0.8
summary_errorbar_capsize = 3
summary_x_margin = 0.58
figure_edge_color = "#2B2B2B"
figure_grid_color = "#E6E6E6"
figure_point_color = "purple"

# Low-saturation, publication-oriented group colors.
# Avoid red/green as the first contrast so group colors do not imply direction.
nature_group_colors = [
    "#4F78B8",
    "#D98C56",
    "#62A86F",
    "#8E79B8",
    "#5BA6A6",
    "#C8A44D",
    "#B76E79",
    "#7A7A7A",
    "#A9B9D8",
    "#D7B49E",
]

"""
Mann-Whitney U 检验每组最少有效数值数
"""
min_group_n = 2

"""
uCDR3 单独处理：
原始 *_uCDR3 是读数，读入后新增 *_uCDR3_ratio = *_uCDR3 / total_uCDR3。
原始 *_uCDR3 不覆盖；统计检验和绘图使用新增的 *_uCDR3_ratio。
"""
convert_ucdr3_to_ratio = 1
ucdr3_count_suffix = "_uCDR3"
ucdr3_ratio_suffix = "_uCDR3_ratio"
ucdr3_ratio_scale = 1.0
ucdr3_chain_order = ["IGH", "IGK", "IGL", "TRA", "TRB", "TRD", "TRG"]

"""
单张 PNG 尺寸控制
"""
figure_width_per_group = 0.34
figure_min_width = 0.92
figure_max_width = 1.95
figure_height = 2.25

"""
分析模式开关
"single" = 单分组模式，使用 data_split_point_begin/over 定义分组列
"cross"  = 交叉分组模式，使用 cross_group_cols 做嵌套交叉分析
"""
analysis_mode = "single"

"""
单分组模式：分类列范围（仅 analysis_mode = "single" 时生效）
"""
data_split_point_begin = "Symptoms"
data_split_point_over = "Symptoms"

"""
参数列范围
"""
param_begin = "IGH_umi_counts"
param_over = "IGHE-IGHG3_CSR_ratio"


"""
移除的 group
"""
remove_list = [0]

"""
交叉分组模式：两个分组字段（仅 analysis_mode = "cross" 时生效）
对字段A每个水平内，用字段B做分组比较；反之亦然
"""
cross_group_cols = ["group_type", "timepoint"]

"""
自定义 group 顺序
"""
arrange_dict = {
    "health_status": [
        "disease",
        "healthy",
    ]
}


def get_filesdir(file_dir):

    if filename_or_file == 0:
        return [file_dir]

    path_list = []

    for root, dirnames, filenames in os.walk(file_dir):
        for filename in filenames:
            if filename.endswith(".csv"):
                path_list.append(os.path.join(root, filename))

    print(path_list)

    return path_list


def _get_column_range(dataframe, begin_col, over_col, range_name):
    columns = dataframe.columns.tolist()

    if begin_col not in columns:
        raise ValueError(f"{range_name} begin field not found: {begin_col}")

    if over_col not in columns:
        raise ValueError(f"{range_name} over field not found: {over_col}")

    begin = columns.index(begin_col)
    over = columns.index(over_col)

    if begin > over:
        raise ValueError(
            f"{range_name} begin field appears after over field: "
            f"{begin_col} > {over_col}"
        )

    return columns[begin : over + 1]


def get_class_dict(dataframe):

    class_dict = {}

    for col_name in _get_column_range(
        dataframe, data_split_point_begin, data_split_point_over, "class columns"
    ):
        col_type_list = []

        if col_name in arrange_dict.keys():
            col_type_list = arrange_dict[col_name]

        else:
            for arg in dataframe[col_name]:
                if pd.isna(arg):
                    continue
                if str(arg).strip() == "" or str(arg).strip().lower() == "nan":
                    continue
                if arg not in col_type_list:
                    col_type_list.append(arg)

            for remove_item in remove_list:
                if remove_item in col_type_list:
                    col_type_list.remove(remove_item)

        class_dict[col_name] = col_type_list

    return class_dict


def pvalue_list_all(df):

    param_cols = get_analysis_param_cols(df)

    print(
        f"Parameter columns used: {len(param_cols)} "
        f"({param_cols[0]} ... {param_cols[-1]})"
    )

    global class_dict

    class_dict = get_class_dict(df)

    p_value_all = {}

    for colname, itemlist in class_dict.items():
        p_value_all[colname] = []

        combination_list = list(combinations(itemlist, 2))

        for cb in combination_list:
            for param_col in param_cols:
                try:
                    group1 = pd.to_numeric(
                        df[df[colname] == cb[0]][param_col], errors="coerce"
                    ).dropna()

                    group2 = pd.to_numeric(
                        df[df[colname] == cb[1]][param_col], errors="coerce"
                    ).dropna()

                    if len(group1) < min_group_n or len(group2) < min_group_n:
                        continue

                    pvalue = mannwhitneyu(
                        group1, group2, alternative="two-sided"
                    ).pvalue

                    p_value_all[colname].append((cb[0], cb[1], param_col, pvalue))

                except Exception:
                    continue

    return p_value_all


def find_tcp(p_value_all):

    in_indice_dict = {}

    pvalue_useful_dict = {}

    for class_col, col_items in class_dict.items():
        pvalue_useful_dict[class_col] = {}

        for pair in p_value_all[class_col]:
            group1 = pair[0]
            group2 = pair[1]
            param = pair[2]
            pvalue = pair[3]

            if pvalue > plot_threshold_pvalue or pd.isna(pvalue):
                continue

            if param not in pvalue_useful_dict[class_col]:
                pvalue_useful_dict[class_col][param] = [(group1, group2, pvalue)]

            else:
                pvalue_useful_dict[class_col][param].append((group1, group2, pvalue))

            if class_col not in in_indice_dict.keys():
                in_indice_dict[class_col] = {param: [group1, group2]}

            elif param not in in_indice_dict[class_col].keys():
                in_indice_dict[class_col][param] = [group1, group2]

            else:
                for item in [group1, group2]:
                    if item not in in_indice_dict[class_col][param]:
                        in_indice_dict[class_col][param].append(item)

    return in_indice_dict, pvalue_useful_dict


def write_significant_txt(p_value_all, stem, subdir="", source=""):
    """Write per-analysis significant pvalue TSV and return rows for consolidation.

    Returns: list of (class_col, group1, group2, param, pvalue, source) tuples.
    """
    txt_dir = ensure_dir(make_output_path(stem, "file", subdir))

    txt_path = os.path.join(txt_dir, "significant_pvalue.txt")

    rows = []

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("class_col\tgroup1\tgroup2\tparam\tpvalue\n")

        for class_col, pair_list in p_value_all.items():
            for group1, group2, param, pvalue in pair_list:
                if pvalue <= sig_threshold_pvalue:
                    f.write(f"{class_col}\t{group1}\t{group2}\t{param}\t{pvalue}\n")
                    rows.append((class_col, group1, group2, param, pvalue, source))

    print(f"Significant txt saved: {txt_path}")

    return rows


def write_consolidated_significant_txt(all_rows):
    """Write consolidated significant pvalue TSV with source column.

    Columns: class_col  group1  group2  param  pvalue  source  (tab-separated)
    """
    if not all_rows:
        print("No significant rows to consolidate.")
        return

    txt_dir = ensure_dir(os.path.join(output_dir, "file"))
    txt_path = os.path.join(txt_dir, "significant_pvalue_all.txt")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("class_col\tgroup1\tgroup2\tparam\tpvalue\tsource\n")
        for row in all_rows:
            f.write("\t".join(str(x) for x in row) + "\n")

    print(f"Consolidated significant txt saved: {txt_path} ({len(all_rows)} rows)")


def make_palette(class_col):

    base_colors = nature_group_colors

    groups = class_dict[class_col]

    palette_dict = {}

    for i, group in enumerate(groups):
        palette_dict[group] = base_colors[i % len(base_colors)]

    return palette_dict


def make_edge_palette(class_col):

    groups = class_dict[class_col]

    palette_dict = {}

    for group in groups:
        palette_dict[group] = figure_edge_color

    return palette_dict


def split_chain_metric(param):
    """Split parameter names in either chain_metric or metric_chain form."""
    parts = str(param).split("_")
    if len(parts) < 2:
        return None, None

    if parts[0] in summary_chain_order:
        return parts[0], "_".join(parts[1:])

    if parts[-1] in summary_chain_order:
        return parts[-1], "_".join(parts[:-1])

    return None, None


def safe_filename(value):
    return re.sub(r"[^0-9A-Za-z._-]+", "_", str(value)).strip("_")


def is_ucdr3_count_param(param):
    return str(param).endswith(ucdr3_count_suffix)


def ucdr3_ratio_col(param):
    return f"{str(param)[: -len(ucdr3_count_suffix)]}{ucdr3_ratio_suffix}"


def get_analysis_param_cols(df):
    """Return plotting/testing columns, adding uCDR3_ratio beside raw uCDR3."""
    raw_param_cols = _get_column_range(df, param_begin, param_over, "parameter columns")
    param_cols = []
    seen = set()

    for param in raw_param_cols:
        for analysis_param in [param]:
            if analysis_param not in seen:
                param_cols.append(analysis_param)
                seen.add(analysis_param)

        if convert_ucdr3_to_ratio == 1 and is_ucdr3_count_param(param):
            ratio_param = ucdr3_ratio_col(param)
            if ratio_param in df.columns and ratio_param not in seen:
                param_cols.append(ratio_param)
                seen.add(ratio_param)

    return param_cols


def apply_ucdr3_ratio(df):
    """Convert chain-level uCDR3 counts to ratios using total uCDR3 per sample."""
    if convert_ucdr3_to_ratio != 1:
        return df

    ucdr3_cols = [
        f"{chain}{ucdr3_count_suffix}"
        for chain in ucdr3_chain_order
        if f"{chain}{ucdr3_count_suffix}" in df.columns
    ]
    if not ucdr3_cols:
        return df

    ucdr3_numeric = df[ucdr3_cols].apply(pd.to_numeric, errors="coerce")
    total_ucdr3 = ucdr3_numeric.sum(axis=1, min_count=1)
    total_ucdr3 = total_ucdr3.where(total_ucdr3 > 0)

    for col in ucdr3_cols:
        df[ucdr3_ratio_col(col)] = ucdr3_numeric[col] / total_ucdr3 * ucdr3_ratio_scale

    print(
        "uCDR3 ratio columns added using row-wise total_uCDR3: "
        + ", ".join(ucdr3_ratio_col(col) for col in ucdr3_cols)
    )

    return df


def display_param_label(param):
    parts = str(param).split("_")
    if len(parts) >= 2 and parts[-1] in summary_chain_order:
        return "_".join(parts[:-1])
    return param


def display_param_filename(param):
    return safe_filename(param)


def p_to_stars(pvalue):
    if pd.isna(pvalue):
        return ""
    if pvalue <= 0.001:
        return "***"
    if pvalue <= 0.01:
        return "**"
    if pvalue <= 0.05:
        return "*"
    return ""


def format_pvalue_label(pvalue):
    if pd.isna(pvalue):
        return ""

    pvalue = float(pvalue)
    if pvalue < 0:
        return ""

    if pvalue < 0.001:
        formatted = f"{pvalue:.2e}"
        formatted = formatted.replace("e-0", "e-").replace("e+0", "e+")
    else:
        formatted = f"{pvalue:.4f}".rstrip("0").rstrip(".")

    return f"p={formatted}"


def get_metric_param_groups(df):
    param_cols = get_analysis_param_cols(df)
    grouped = {}
    first_seen = {}

    for index, param in enumerate(param_cols):
        chain, metric = split_chain_metric(param)
        if not chain or not metric:
            continue
        if chain not in summary_chain_order:
            continue
        if metric not in grouped:
            grouped[metric] = []
            first_seen[metric] = index
        grouped[metric].append((chain, param, index))

    chain_rank = {chain: i for i, chain in enumerate(summary_chain_order)}
    for metric, items in grouped.items():
        grouped[metric] = sorted(
            items,
            key=lambda item: (
                chain_rank.get(item[0], len(chain_rank)),
                item[2],
            ),
        )

    return {
        metric: [(chain, param) for chain, param, _ in items]
        for metric, items in sorted(
            grouped.items(), key=lambda item: first_seen[item[0]]
        )
        if len(items) >= 2
    }


def draw_sig_bracket(ax, x1, x2, y, h, text):
    ax.plot(
        [x1, x1, x2, x2],
        [y, y + h, y + h, y],
        color=figure_edge_color,
        lw=0.8,
    )
    ax.text(
        (x1 + x2) / 2,
        y + h,
        text,
        ha="center",
        va="bottom",
        fontsize=8,
        fontweight="semibold",
        color=figure_edge_color,
    )


def draw_sig_bracket_to_tops(ax, x1, x2, y_top, y1, y2, text):
    ax.plot(
        [x1, x1, x2, x2],
        [y1, y_top, y_top, y2],
        color=figure_edge_color,
        lw=0.8,
    )
    ax.text(
        (x1 + x2) / 2,
        y_top,
        text,
        ha="center",
        va="bottom",
        fontsize=8,
        fontweight="semibold",
        color=figure_edge_color,
    )


def add_single_plot_significance(ax, concat_df, class_col, param, pvalue_list):
    """Draw significance brackets on one boxplot for significant pairwise tests."""
    groups = [
        group for group in class_dict[class_col] if group in concat_df[class_col].values
    ]
    group_positions = {str(group): i for i, group in enumerate(groups)}

    sig_pairs = []
    for group1, group2, pvalue in pvalue_list:
        if not p_to_stars(pvalue):
            continue
        p_label = format_pvalue_label(pvalue)
        if not p_label:
            continue
        x1 = group_positions.get(str(group1))
        x2 = group_positions.get(str(group2))
        if x1 is None or x2 is None:
            continue
        sig_pairs.append((x1, x2, p_label))

    if not sig_pairs:
        return

    values = pd.to_numeric(concat_df[param], errors="coerce").dropna()
    if values.empty:
        return

    y_min = min(0.0, float(values.min()))
    y_max = float(values.max())
    if y_max <= y_min:
        y_max = y_min + 1.0

    y_span = y_max - y_min
    bracket_h = y_span * 0.035
    bracket_step = y_span * 0.13

    for level, (x1, x2, stars) in enumerate(sig_pairs):
        y = y_max + bracket_step * level
        draw_sig_bracket(ax, x1, x2, y, bracket_h, stars)

    ax.set_ylim(y_min, y_max + len(sig_pairs) * bracket_step + bracket_h * 2)


def plot_chain_metric_summaries(df, p_value_all, stem, class_col, subdir=""):
    metric_groups = get_metric_param_groups(df)
    if not metric_groups:
        return

    groups = [group for group in class_dict[class_col] if group in df[class_col].values]
    if len(groups) < 2:
        return

    palette_dict = make_palette(class_col)
    p_lookup = {}
    for group1, group2, param, pvalue in p_value_all.get(class_col, []):
        p_lookup[(str(group1), str(group2), param)] = pvalue
        p_lookup[(str(group2), str(group1), param)] = pvalue

    out_dir = ensure_dir(make_output_path(stem, "figure", subdir, class_col, "summary"))

    for metric, chain_params in metric_groups.items():
        n_groups = len(groups)

        summary_rows = []
        drawable_chain_params = []
        for chain, param in chain_params:
            chain_has_values = False
            for group in groups:
                values = pd.to_numeric(
                    df[df[class_col] == group][param], errors="coerce"
                ).dropna()
                if not values.empty:
                    chain_has_values = True
                for value in values:
                    summary_rows.append(
                        {
                            "chain": chain,
                            "group": group,
                            "value": value,
                        }
                    )
            if chain_has_values:
                drawable_chain_params.append((chain, param))

        if not summary_rows:
            continue

        chain_params = drawable_chain_params
        chains = [chain for chain, _ in chain_params]
        n_chains = len(chains)
        summary_df = pd.DataFrame(summary_rows)
        fig_width = max(summary_fig_width, 0.58 * n_chains + 1.75)

        fig, ax = plt.subplots(figsize=(fig_width, summary_fig_height))
        fig.subplots_adjust(left=0.16, right=0.80, top=0.88, bottom=0.26)

        bar_span = min(summary_bar_width, 0.88)
        bar_step = bar_span / max(n_groups, 1)
        bar_width = bar_step * 0.86
        offsets = [(i - (n_groups - 1) / 2) * bar_step for i in range(n_groups)]
        bar_centers = {}
        bar_tops = {}
        legend_handles = []

        for group_index, group in enumerate(groups):
            color = palette_dict.get(group, nature_group_colors[0])
            legend_handles.append(
                mpl.patches.Patch(
                    facecolor=color,
                    edgecolor=figure_edge_color,
                    linewidth=summary_bar_edge_width,
                    label=str(group),
                )
            )

            for chain_index, chain in enumerate(chains):
                values = pd.to_numeric(
                    summary_df[
                        (summary_df["chain"] == chain) & (summary_df["group"] == group)
                    ]["value"],
                    errors="coerce",
                ).dropna()
                if values.empty:
                    continue

                center = chain_index + offsets[group_index]
                bar_centers[(chain_index, str(group))] = center
                mean_value = float(values.mean())
                sem_value = float(values.sem()) if len(values) > 1 else 0.0
                if pd.isna(sem_value):
                    sem_value = 0.0
                bar_tops[(chain_index, str(group))] = mean_value + sem_value

                ax.bar(
                    center,
                    mean_value,
                    width=bar_width,
                    color=color,
                    edgecolor=figure_edge_color,
                    linewidth=summary_bar_edge_width,
                    yerr=sem_value,
                    capsize=summary_errorbar_capsize,
                    error_kw={
                        "ecolor": figure_edge_color,
                        "elinewidth": summary_errorbar_line_width,
                        "capthick": summary_errorbar_line_width,
                    },
                    zorder=2,
                )

        ax.legend(
            legend_handles,
            [str(group) for group in groups],
            loc="upper left",
            bbox_to_anchor=(1.02, 1.0),
            borderaxespad=0,
            fontsize=8,
            handlelength=1.2,
            frameon=False,
        )

        values_all = pd.to_numeric(summary_df["value"], errors="coerce").dropna()
        chain_value_max = {
            chain: pd.to_numeric(
                summary_df[summary_df["chain"] == chain]["value"], errors="coerce"
            )
            .dropna()
            .max()
            for chain in chains
        }

        ax.set_xticks(range(n_chains))
        ax.set_xticklabels(chains, fontsize=9, fontweight="semibold")
        ax.set_xlim(-summary_x_margin, n_chains - 1 + summary_x_margin)
        ax.set_ylabel(display_param_label(metric), fontsize=10.5, fontweight="semibold")
        ax.set_xlabel("")
        ax.tick_params(axis="y", labelsize=8, length=3, width=0.8)
        ax.tick_params(axis="x", length=0)
        ax.grid(
            axis="y",
            color=figure_grid_color,
            linewidth=0.35,
            alpha=0.75,
            zorder=0,
        )
        ax.set_axisbelow(True)

        if values_all.empty:
            plt.close(fig)
            continue

        y_min = float(values_all.min())
        y_max = float(values_all.max())
        if y_max <= y_min:
            y_max = y_min + 1.0
        y_span = y_max - y_min
        bracket_h = y_span * 0.035
        bracket_step = y_span * 0.075
        bracket_gap = y_span * 0.035
        used_levels = [0] * n_chains
        bracket_tops = []

        for chain_index, (chain, param) in enumerate(chain_params):
            local_y_max = chain_value_max.get(chain)
            if pd.isna(local_y_max):
                continue
            pair_level = 0
            for group1, group2 in combinations(groups, 2):
                pvalue = p_lookup.get((str(group1), str(group2), param))
                stars = p_to_stars(pvalue)
                if not stars:
                    continue
                x1 = bar_centers.get((chain_index, str(group1)))
                x2 = bar_centers.get((chain_index, str(group2)))
                if x1 is None or x2 is None:
                    continue
                y1 = bar_tops.get((chain_index, str(group1)), float(local_y_max))
                y2 = bar_tops.get((chain_index, str(group2)), float(local_y_max))
                y = max(y1, y2) + bracket_gap + bracket_step * pair_level
                draw_sig_bracket_to_tops(ax, x1, x2, y, y1, y2, stars)
                bracket_tops.append(y + bracket_h)
                pair_level += 1
            used_levels[chain_index] = pair_level

        lower_pad = y_span * 0.08
        upper_target = max([y_max] + bracket_tops) if bracket_tops else y_max
        upper_pad = y_span * 0.08
        ax.set_ylim(y_min - lower_pad, upper_target + upper_pad)

        facecolor = "none" if transparent_background == 1 else "white"
        if transparent_background == 1:
            fig.patch.set_alpha(0)
            ax.set_facecolor("none")
        else:
            fig.patch.set_alpha(1)
            ax.set_facecolor("white")

        for ext in export_formats:
            fig_path = os.path.join(
                out_dir, f"{display_param_filename(metric)}_summary.{ext}"
            )
            fig.savefig(
                fig_path,
                bbox_inches="tight",
                pad_inches=save_pad_inches,
                dpi=600,
                transparent=transparent_background == 1,
                facecolor=facecolor,
            )

        plt.close(fig)


def format_y_axis_ticks(ax):
    ymin, ymax = ax.get_ylim()
    max_abs = max(abs(ymin), abs(ymax))

    if max_abs == 0:
        return

    if (
        max_abs < compact_y_tick_threshold_low
        or max_abs >= compact_y_tick_threshold_high
    ):
        exponent = int(math.floor(math.log10(max_abs)))
        scale = 10**exponent

        def compact_formatter(value, position):
            scaled = value / scale
            if abs(scaled) >= 10:
                return f"{scaled:.0f}"
            return f"{scaled:.1f}"

        ax.yaxis.set_major_formatter(mticker.FuncFormatter(compact_formatter))
        ax.yaxis.offsetText.set_visible(False)
        ax.text(
            0.01,
            0.985,
            rf"$\times 10^{{{exponent}}}$",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=tick_font_size,
            fontweight="semibold",
        )


def adjust_y_label_away_from_ticks(ax, y_position, gap_px=None):
    """Move the y-axis label left if it overlaps wide y tick labels."""
    gap_px = y_label_tick_gap_px if gap_px is None else gap_px
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    tick_bboxes = [
        tick.get_window_extent(renderer)
        for tick in ax.get_yticklabels()
        if tick.get_visible() and tick.get_text()
    ]
    if not tick_bboxes:
        return

    label = ax.yaxis.get_label()
    label_bbox = label.get_window_extent(renderer)
    tick_left = min(bbox.x0 for bbox in tick_bboxes)
    desired_label_right = tick_left - gap_px

    if label_bbox.x1 <= desired_label_right:
        return

    label_center_y = ax.transAxes.transform((0, y_position))[1]
    desired_label_center_x = desired_label_right - label_bbox.width / 2
    desired_x = ax.transAxes.inverted().transform(
        (desired_label_center_x, label_center_y)
    )[0]

    current_x = label.get_position()[0]
    ax.yaxis.set_label_coords(min(current_x, desired_x), y_position)
    fig.canvas.draw()


def _calculate_consistent_dimensions(param_names, n_groups):
    """Pre-compute uniform figure dimensions so every plot shares the same proportions.

    The box plot area (right side) keeps a fixed width; the left gutter does NOT
    expand.  Instead, the y-axis label is shifted downward for long parameter
    names so the rotated text fits without being clipped at the top.
    """
    max_label_len = max((len(str(p)) for p in param_names), default=15)

    plot_width = min(
        max(figure_width_per_group * n_groups, figure_min_width),
        figure_max_width,
    )
    y_label_gutter = max(y_label_gutter_width, 0.82)
    fig_height = figure_height
    fig_width = plot_width + y_label_gutter
    y_label_x_pos = y_label_x_position

    # 长参数名时 Y 轴标签向下移动，而非扩展左侧边距
    # 默认居中 0.5；名字每超过 15 个字符多下移 0.008（axes 坐标系）
    y_label_y_pos = 0.5 - max(0, max_label_len - 15) * 0.008
    y_label_y_pos = max(y_label_y_pos, 0.28)  # 不低于 0.28

    return {
        "plot_width": plot_width,
        "y_label_gutter": y_label_gutter,
        "fig_height": fig_height,
        "fig_width": fig_width,
        "y_label_x_position": y_label_x_pos,
        "y_label_y_position": y_label_y_pos,
    }


def plotboxs_mat_mutiple(
    df,
    pvalue_list,
    class_col,
    param,
    filename,
    pvalue_pair_dict,
    map_list,
    dims=None,
):

    plot_df = df[["sample", class_col, param]].copy()

    plot_df[param] = pd.to_numeric(plot_df[param], errors="coerce")

    plot_df = plot_df.dropna(subset=[class_col, param])

    concat_df = plot_df.iloc[:0]

    for col_type in class_dict[class_col]:
        filtered = plot_df[plot_df[class_col] == col_type]
        concat_df = pd.concat([concat_df, filtered], ignore_index=True)

    if dims is not None:
        plot_width = dims["plot_width"]
        y_label_gutter = dims["y_label_gutter"]
        fig_height = dims["fig_height"]
        fig_width = dims["fig_width"]
        y_label_x_pos = dims["y_label_x_position"]
        y_label_y_pos = dims["y_label_y_position"]
    else:
        plot_width = min(
            max(figure_width_per_group * len(class_dict[class_col]), figure_min_width),
            figure_max_width,
        )
        y_label_gutter = max(y_label_gutter_width, 0.82)
        fig_height = min(max(figure_height, 1.4 + 0.055 * len(str(param))), 4.5)
        fig_width = plot_width + y_label_gutter
        y_label_x_pos = y_label_x_position
        y_label_y_pos = 0.5

    # 根据 x 轴标签最长字符数动态计算底部边距，避免长标签被截断
    max_xtick_len = max((len(str(label)) for label in class_dict[class_col]), default=5)
    # 旋转 90° 后每字符垂直延伸量 ≈ 0.06 inch/char（8pt 字号），加轴线/留白 0.15 inch
    bottom_inches = max_xtick_len * 0.06 + 0.15
    bottom = max(0.20, min(0.55, bottom_inches / fig_height))

    fig, ax_box = plt.subplots(figsize=(fig_width, fig_height))
    fig.subplots_adjust(
        left=y_label_gutter / fig_width,
        right=0.985,
        top=0.98,
        bottom=bottom,
    )

    sns.set_style("white")
    palette_dict = make_palette(class_col)

    sns.boxplot(
        y=param,
        x=class_col,
        data=concat_df,
        linewidth=0.8,
        width=0.5,
        palette=palette_dict,
        showfliers=False,
        ax=ax_box,
    )

    sns.stripplot(
        y=param,
        x=class_col,
        data=concat_df,
        color=figure_point_color,
        jitter=True,
        alpha=0.75,
        size=3,
        linewidth=0,
        edgecolor="none",
        ax=ax_box,
    )

    for ppair_value in pvalue_list:
        vs_str = str(ppair_value[0]) + " VS " + str(ppair_value[1])

        if vs_str not in map_list:
            map_list.append(vs_str)

        if vs_str not in pvalue_pair_dict["cate"]:
            pvalue_pair_dict["cate"].append(vs_str)

        if param not in pvalue_pair_dict.keys():
            pvalue_pair_dict[param] = [
                (map_list.index(vs_str), float("%.4g" % ppair_value[2]))
            ]

        else:
            pvalue_pair_dict[param].append(
                (map_list.index(vs_str), float("%.4g" % ppair_value[2]))
            )

    font = {"weight": "semibold", "size": axis_label_font_size}

    ax_box.set_ylabel(
        display_param_label(param),
        fontdict=font,
        labelpad=10,
        rotation=90,
        va="center",
    )
    ax_box.yaxis.set_label_coords(y_label_x_pos, y_label_y_pos)

    # 去掉横坐标标题
    ax_box.set_xlabel("")

    ax_box.set_xticklabels(labels=ax_box.get_xticklabels(), rotation=90)

    ax_box.tick_params(labelsize=tick_font_size, length=0)
    plt.setp(ax_box.get_xticklabels(), fontweight="semibold")
    plt.setp(ax_box.get_yticklabels(), fontweight="semibold")
    add_single_plot_significance(ax_box, concat_df, class_col, param, pvalue_list)
    format_y_axis_ticks(ax_box)
    adjust_y_label_away_from_ticks(ax_box, y_label_y_pos)
    ax_box.grid(axis="y", color=figure_grid_color, linewidth=0.35, alpha=0.75)
    ax_box.set_axisbelow(True)

    output_stem, output_subdir = split_output_context(filename)
    figure_path = ensure_dir(
        make_output_path(output_stem, "figure", output_subdir, class_col)
    )

    # 背景透明控制
    facecolor = "none" if transparent_background == 1 else "white"
    if transparent_background == 1:
        ax_box.figure.patch.set_alpha(0)

        ax_box.set_facecolor("none")

    else:
        ax_box.figure.patch.set_alpha(1)

        ax_box.set_facecolor("white")

    for ext in export_formats:
        fig_path = os.path.join(figure_path, f"{display_param_filename(param)}.{ext}")
        ax_box.figure.savefig(
            fig_path,
            bbox_inches=save_bbox_inches,
            pad_inches=save_pad_inches,
            dpi=600,
            transparent=transparent_background == 1,
            facecolor=facecolor,
        )

    plt.close(ax_box.figure)

    csv_path = ensure_dir(
        make_output_path(output_stem, "file", output_subdir, class_col, "data")
    )

    concat_df.to_csv(
        os.path.join(csv_path, display_param_filename(param) + ".csv"), index=False
    )


def _get_ordered_values(df, col, arrange_dict):
    """获取组的排序列表，优先使用 arrange_dict，否则按首次出现顺序去重。"""
    if col in arrange_dict:
        return [v for v in arrange_dict[col] if v in df[col].values]
    else:
        seen = []
        for v in df[col]:
            if v not in seen:
                seen.append(v)
        return seen


def _run_analysis(df, stem, group_col, subdir, stem_filename):
    """对 df 以 group_col 做分组，运行完整分析，输出到 boxplot/<subdir>/<stem>/

    Returns: list of (class_col, group1, group2, param, pvalue, source) tuples.
    """
    global data_split_point_begin, data_split_point_over

    old_begin = data_split_point_begin
    old_over = data_split_point_over

    data_split_point_begin = group_col
    data_split_point_over = group_col

    p_value_all = pvalue_list_all(df)

    source = f"{stem}/{subdir}" if subdir else stem
    sig_rows = write_significant_txt(p_value_all, stem, subdir, source=source)

    in_indice_dict, pvalue_useful_dict = find_tcp(p_value_all)

    for class_col, col_item_dict in in_indice_dict.items():
        # --- pre-compute consistent dimensions for all params in this class_col ---
        param_names = list(col_item_dict.keys())
        n_groups = len(class_dict.get(class_col, []))
        dims = _calculate_consistent_dimensions(param_names, n_groups)

        pvalue_pair_dict = {"cate": []}

        map_list = []

        for param, col_types in col_item_dict.items():
            pvalue_list = pvalue_useful_dict[class_col][param]

            plotboxs_mat_mutiple(
                df,
                pvalue_list,
                class_col,
                param,
                os.path.join(stem, subdir),
                pvalue_pair_dict,
                map_list,
                dims=dims,
            )

        cate_len = len(pvalue_pair_dict["cate"])

        first_flag = True

        for key, p_items in pvalue_pair_dict.items():
            if first_flag:
                first_flag = False

                continue

            p_list = [0] * cate_len

            for p_tuple in p_items:
                p_list[p_tuple[0]] = p_tuple[1]

            pvalue_pair_dict[key] = p_list

        df_p = pd.DataFrame(pvalue_pair_dict)

        pvalue_dir = ensure_dir(make_output_path(stem, "file", subdir))
        df_p.to_csv(os.path.join(pvalue_dir, f"pvalue_{class_col}.csv"), index=False)

    plot_chain_metric_summaries(df, p_value_all, stem, group_col, subdir=subdir)

    data_split_point_begin = old_begin
    data_split_point_over = old_over

    return sig_rows


def draw(data_path):
    """Process one CSV file. Returns list of significant rows for consolidation."""
    filepath, filename = os.path.split(data_path)

    stem, suffix = os.path.splitext(filename)

    df = pd.read_csv(data_path)
    df = apply_ucdr3_ratio(df)

    all_sig_rows = []

    if analysis_mode == "cross":
        col1, col2 = cross_group_cols[0], cross_group_cols[1]

        # 对 col1 每个水平（按 arrange_dict 排序），以 col2 做分组
        outer_vals1 = _get_ordered_values(df, col1, arrange_dict)
        for val1 in outer_vals1:
            subset = df[df[col1] == val1].copy()
            if len(subset) < 2:
                continue
            rows = _run_analysis(subset, stem, col2, f"{col1}={val1}", filename)
            all_sig_rows.extend(rows)

        # 对 col2 每个水平（按 arrange_dict 排序），以 col1 做分组
        outer_vals2 = _get_ordered_values(df, col2, arrange_dict)
        for val2 in outer_vals2:
            subset = df[df[col2] == val2].copy()
            if len(subset) < 2:
                continue
            rows = _run_analysis(subset, stem, col1, f"{col2}={val2}", filename)
            all_sig_rows.extend(rows)
    else:
        p_value_all = pvalue_list_all(df)

        # 输出显著性 txt
        sig_rows = write_significant_txt(p_value_all, stem, source=stem)
        all_sig_rows.extend(sig_rows)

        in_indice_dict, pvalue_useful_dict = find_tcp(p_value_all)

        for class_col, col_item_dict in in_indice_dict.items():
            # --- pre-compute consistent dimensions for all params in this class_col ---
            param_names = list(col_item_dict.keys())
            n_groups = len(class_dict.get(class_col, []))
            dims = _calculate_consistent_dimensions(param_names, n_groups)

            pvalue_pair_dict = {"cate": []}

            map_list = []

            for param, col_types in col_item_dict.items():
                pvalue_list = pvalue_useful_dict[class_col][param]

                plotboxs_mat_mutiple(
                    df,
                    pvalue_list,
                    class_col,
                    param,
                    stem,
                    pvalue_pair_dict,
                    map_list,
                    dims=dims,
                )

            cate_len = len(pvalue_pair_dict["cate"])

            first_flag = True

            for key, p_items in pvalue_pair_dict.items():
                if first_flag:
                    first_flag = False

                    continue

                p_list = [0] * cate_len

                for p_tuple in p_items:
                    p_list[p_tuple[0]] = p_tuple[1]

                pvalue_pair_dict[key] = p_list

            df_p = pd.DataFrame(pvalue_pair_dict)

            pvalue_dir = ensure_dir(make_output_path(stem, "file"))
            df_p.to_csv(
                os.path.join(pvalue_dir, f"pvalue_{class_col}.csv"),
                index=False,
            )

        plot_chain_metric_summaries(df, p_value_all, stem, data_split_point_begin)

    return all_sig_rows


if not os.path.exists(output_dir):
    os.mkdir(output_dir)


all_consolidated_rows = []
for data_path in get_filesdir(file_dir):
    print(f"Processing: {data_path}")

    rows = draw(data_path)
    all_consolidated_rows.extend(rows)

# sort: source, class_col, group1, group2, param
all_consolidated_rows.sort(key=lambda x: (x[5], x[0], x[1], x[2], x[3]))
write_consolidated_significant_txt(all_consolidated_rows)

print("Done.")
