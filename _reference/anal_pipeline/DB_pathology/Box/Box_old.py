# -*- coding: utf-8 -*-
import pandas as pd
from scipy.stats import mannwhitneyu
from itertools import combinations
import seaborn as sns
import os
import math
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.ticker as mticker

axis_label_font_size = 10.5
tick_font_size = 8
y_label_gutter_width = 0.60
y_label_x_position = -0.50
save_pad_inches = 0.06
save_bbox_inches = None
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
        "axes.linewidth": 0.8,
        "legend.frameon": False,
        "figure.dpi": 120,
        "savefig.dpi": 600,
    }
)

file_dir = "/data/scAnalyis/260416/newanal/personal/DB_pathology/specify_ratio"

"""
if filename_or_file = 1, input is a dirname
if filename_or_file = 0, input will be a filename
"""
filename_or_file = 1

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
output_dir = "boxplot_test"

"""
Mann-Whitney U 检验每组最少有效数值数
"""
min_group_n = 2

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
analysis_mode = "cross"

"""
单分组模式：分类列范围（仅 analysis_mode = "single" 时生效）
"""
data_split_point_begin = "group_type"
data_split_point_over = "timepoint"

"""
参数列范围
"""
param_begin = "TRA_ratio_VDJdb"
param_over = "TRB_ratio_McPASTCR"


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
    "group_type": [
        "control",
        "experiment",
    ],
    "timepoint": ["before", "after"],
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
                if arg not in col_type_list:
                    col_type_list.append(arg)

            for remove_item in remove_list:
                if remove_item in col_type_list:
                    col_type_list.remove(remove_item)

        class_dict[col_name] = col_type_list

    return class_dict


def pvalue_list_all(df):

    param_cols = _get_column_range(df, param_begin, param_over, "parameter columns")

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
    txt_dir = os.path.join(output_dir, stem, subdir)

    os.makedirs(txt_dir, exist_ok=True)

    txt_path = os.path.join(txt_dir, f"{stem}_significant_pvalue.txt")

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

    txt_path = os.path.join(output_dir, "significant_pvalue_all.txt")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("class_col\tgroup1\tgroup2\tparam\tpvalue\tsource\n")
        for row in all_rows:
            f.write("\t".join(str(x) for x in row) + "\n")

    print(f"Consolidated significant txt saved: {txt_path} ({len(all_rows)} rows)")


def make_palette(class_col):

    base_colors = [
        "#4C72B0",
        "#DD8452",
        "#55A868",
        "#C44E52",
        "#8172B2",
        "#937860",
        "#DA8BC3",
        "#8C8C8C",
        "#CCB974",
        "#64B5CD",
    ]

    groups = class_dict[class_col]

    palette_dict = {}

    for i, group in enumerate(groups):
        palette_dict[group] = base_colors[i % len(base_colors)]

    return palette_dict


def make_edge_palette(class_col):

    base_colors = [
        "#4C72B0",
        "#DD8452",
        "#55A868",
        "#C44E52",
        "#8172B2",
        "#937860",
        "#DA8BC3",
        "#8C8C8C",
        "#CCB974",
        "#64B5CD",
    ]

    groups = class_dict[class_col]

    palette_dict = {}

    for i, group in enumerate(groups):
        palette_dict[group] = base_colors[i % len(base_colors)]

    return palette_dict


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
    y_label_gutter = y_label_gutter_width
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

    plot_df = df[["Sample", class_col, param]].copy()

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
        y_label_gutter = y_label_gutter_width
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
        color="purple",
        jitter=True,
        alpha=0.75,
        size=3,
        linewidth=0,
        edgecolor="none",
        ax=ax_box,
    )

    for ppair_value in pvalue_list:
        vs_str = ppair_value[0] + " VS " + ppair_value[1]

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
        param,
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
    format_y_axis_ticks(ax_box)
    ax_box.grid(axis="y", color="#D9D9D9", linewidth=0.35, alpha=0.75)
    ax_box.set_axisbelow(True)

    path = os.path.join(output_dir, filename)

    os.makedirs(path, exist_ok=True)

    path = os.path.join(path, class_col)

    os.makedirs(path, exist_ok=True)

    # 背景透明控制
    facecolor = "none" if transparent_background == 1 else "white"
    if transparent_background == 1:
        ax_box.figure.patch.set_alpha(0)

        ax_box.set_facecolor("none")

    else:
        ax_box.figure.patch.set_alpha(1)

        ax_box.set_facecolor("white")

    for ext in export_formats:
        fig_path = os.path.join(path, f"{param}.{ext}")
        ax_box.figure.savefig(
            fig_path,
            bbox_inches=save_bbox_inches,
            pad_inches=save_pad_inches,
            dpi=600,
            transparent=transparent_background == 1,
            facecolor=facecolor,
        )

    plt.close(ax_box.figure)

    csv_path = os.path.join(path, "csvfile")

    os.makedirs(csv_path, exist_ok=True)

    concat_df.to_csv(os.path.join(csv_path, param + ".csv"), index=False)


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

        df_p.to_csv(
            os.path.join(
                output_dir, stem, subdir, stem_filename + "_" + class_col + ".csv"
            ),
            index=False,
        )

    data_split_point_begin = old_begin
    data_split_point_over = old_over

    return sig_rows


def draw(data_path):
    """Process one CSV file. Returns list of significant rows for consolidation."""
    filepath, filename = os.path.split(data_path)

    stem, suffix = os.path.splitext(filename)

    df = pd.read_csv(data_path)

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

            df_p.to_csv(
                os.path.join(output_dir, stem, filename + "_" + class_col + ".csv"),
                index=False,
            )

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
