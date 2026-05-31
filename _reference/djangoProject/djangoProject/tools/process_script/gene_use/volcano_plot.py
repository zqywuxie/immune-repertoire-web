import os
import pandas as pd
from itertools import combinations
import numpy as np
import pymongo
from scipy.stats import mannwhitneyu
import seaborn as sns
import matplotlib.pyplot as plt
import warnings
from typing import List, Dict, Tuple, Any

warnings.filterwarnings('ignore')

def get_data(path_list: List[str]) -> Tuple[Dict[Tuple[str, str], Dict[str, List[float]]], Dict[Tuple[str, str], List[str]], List[str]]:
    """
    计算所有样本路径下的差异分析数据（Fold Change 和 P 值）。
    """
    files = path_list
    volcano_dict = {}
    df_index = {}
    # save_path_list = []
    for file in files:
        df = pd.read_csv(file)
        save_path = os.path.split(file)[0]
        # print(df.head())
        df = df.fillna(0)
        category_cbs = list(combinations(df.Category.unique(), 2))
        data_begin = df.columns[list(df.columns).index("Category") + 1:]
        for category_cb in category_cbs:
            if category_cb not in volcano_dict.keys():
                volcano_dict[category_cb] = {"fc": [], "pvalue": []}
                df_index[category_cb] = []
            pvalue_list = []
            df_use_gp = df[df.Category.isin(category_cb)].groupby(by="Category")
            df_use_mean = df_use_gp[data_begin].mean()
            fc = np.log2(df_use_mean.iloc[0] / df_use_mean.iloc[1])
            for col in data_begin:
                x = df[df.Category == category_cb[0]][col]
                y = df[df.Category == category_cb[1]][col]
                pvalue_list.append(mannwhitneyu(x, y, alternative="two-sided").pvalue)
            volcano_dict[category_cb]['fc'] += fc.values.tolist()
            volcano_dict[category_cb]['pvalue'] += pvalue_list
            df_index[category_cb] += fc.index.tolist()
    return volcano_dict, df_index, [save_path for i in range(len(volcano_dict))]


def volcano_plot(volcano_dict_item: Dict[str, List[float]], df_index_item: List[str], cb: Tuple[str, str], save_path: str) -> None:
    """
    根据差异分析结果绘制并保存火山图。
    """
    volcano_df = pd.DataFrame(volcano_dict_item, index=df_index_item)
    volcano_df["pvalue_log10"] = -np.log10(volcano_df["pvalue"])
    volcano_df.dropna(inplace=True)
    sns.set_theme(style="white", font='Arial')
    # 设置pvalue和logFC的阈值
    cut_off_pvalue = 0.05
    cut_off_pvalue_sig = 0.005
    cut_off_logFC = 0

    xmin = -2
    xmax = 2
    ymin = 0
    ymax = 5

    volcano_df.loc[(volcano_df.fc > cut_off_logFC) & (volcano_df.pvalue < cut_off_pvalue) & (
            cut_off_pvalue_sig < volcano_df.pvalue), 'Group'] = 'Up'
    volcano_df.loc[(volcano_df.fc < -cut_off_logFC) & (volcano_df.pvalue < cut_off_pvalue) & (
            cut_off_pvalue_sig < volcano_df.pvalue), 'Group'] = 'Down'
    volcano_df.loc[(volcano_df.fc > cut_off_logFC) & (volcano_df.pvalue < cut_off_pvalue_sig), 'Group'] = 'Sig Up'
    volcano_df.loc[(volcano_df.fc < -cut_off_logFC) & (volcano_df.pvalue < cut_off_pvalue_sig), 'Group'] = 'Sig Down'
    volcano_df.loc[(volcano_df.fc >= -cut_off_logFC) & (volcano_df.fc <= cut_off_logFC) | (
            volcano_df.pvalue >= cut_off_pvalue), 'Group'] = 'Normal'
    ax = sns.scatterplot(x="fc", y="pvalue_log10",
                         hue='Group',
                         hue_order=('Sig Down', 'Down', 'Normal', 'Up', 'Sig Up'),
                         palette=("#0000FF", "#377EB8", "grey", "#E41A1C", "#8B0000"),

                         data=volcano_df)
    ax.spines['right'].set_visible(False)  # 去掉右边框
    ax.spines['top'].set_visible(False)  # 去掉上边框

    ax.vlines(-cut_off_logFC, ymin, ymax, color='black', linestyle='dashed', linewidth=2)  # 画竖直线
    ax.vlines(cut_off_logFC, ymin, ymax, color='black', linestyle='dashed', linewidth=2)  # 画竖直线
    ax.hlines(-np.log10(cut_off_pvalue), xmin, xmax, color='black', linestyle='dashed', linewidth=2)  # 画竖水平线

    font = {"style": 'italic', "weight": "bold"}

    for row in volcano_df.iterrows():
        if row[1]["pvalue"] < 0.005:
            # plt.text(row[1]["fc"], row[1]["pvalue_log10"]+0.1, row[0], fontdict=font,fontsize=5)
            ax.annotate(row[0], xy=(row[1]["fc"], row[1]["pvalue_log10"]),
                        xytext=(row[1]["fc"], row[1]["pvalue_log10"] + 0.1))
    # ax.set_xticks(range(xmin, xmax, 4))# 设置x轴刻度
    # ax.set_yticks(range(ymin, ymax, 0.5))# 设置y轴刻度
    ax.set_ylabel('-log10(pvalue)', fontweight='bold', fontdict={"size": 12})  # 设置y轴标签
    ax.set_xlabel('log2(fold change)', fontweight='bold', fontdict={"size": 12})  # 设置x轴标签
    ax.legend().set_visible(False)
    ax.xaxis.set_tick_params(which='both', bottom=True, top=False, direction='out', width=1, length=2)
    ax.yaxis.set_tick_params(which='both', bottom=True, top=False, direction='out', width=1, length=2)
    figure = ax.get_figure()
    plt.xticks(fontweight='semibold', size=12)
    plt.yticks(fontweight='semibold', size=12)
    # chain = file.split("/")[-1][:-4]+"/"
    # if not os.path.exists(chain):
    #     os.makedirs(chain)
    # figure.savefig(chain+category_cb[0]+"___"+category_cb[1]+".png")
    from appone.constant import PROJECT_FILE
    if not os.path.exists(f"{save_path}/volcano/Fig/"):
        os.makedirs(f"{save_path}/volcano/Fig/")
    figure.savefig(f"{save_path}/volcano/Fig/" + cb[0] + "_VS_" + cb[1] + ".png", dpi=300)
    ax.cla()


def list_files_in_directory(directory_path: str) -> List[str]:
    """
    列出指定目录下的所有文件路径。
    """
    try:
        # List all entries in the directory
        all_entries = os.listdir(directory_path)
        # Filter out directories, keep only files
        files = [entry for entry in all_entries if os.path.isfile(os.path.join(directory_path, entry))]
        return files
    except Exception as e:
        return str(e)


# plot_file_path = ["./usage_cate/usage/0Vusage/","./usage_cate/usage/0Jusage/","./usage_cate/usage/0VJusage/"]
# group_list = ["group1","group2","group3"]

def start_func(projectName: str) -> None:
    """
    启动差异分析火山图绘制流程。
    """
    from appone.constant import PROJECT_FILE, DBURL
    plot_file_path = [f"{PROJECT_FILE}/{projectName}/gene_usage/usage_cate/usage/0Vusage/",
                      f"{PROJECT_FILE}/{projectName}/gene_usage/usage_cate/usage/0Jusage/",
                      f"{PROJECT_FILE}/{projectName}/gene_usage/usage_cate/usage/0VJusage/"
                      ]
    group_list = list(pymongo.MongoClient(DBURL, maxidletimems=120000)[projectName]['groupSpecification']
                      .find({'name': projectName})[0]["groupSpecification"].keys())

    for plot_path in plot_file_path:
        directory_path_list = []
        for group in group_list:
            directory_path_list.append(plot_path + group)
            path_list = []
            for directory_path in directory_path_list:
                files = list_files_in_directory(directory_path)
                for file in files:
                    path_list.append(os.path.join(directory_path, file))
            volcano_dict, df_index, sava_path_list = get_data(path_list=path_list)
            for (key, volcano_dict_item), save_path in zip(volcano_dict.items(), sava_path_list):
                volcano_plot(volcano_dict_item, df_index[key], key, save_path)
            for (key, volcano_dict_item), save_path in zip(volcano_dict.items(), sava_path_list):
                save_df = pd.DataFrame(index=df_index[key], columns=['fc', 'pvalue'])
                save_df["fc"] = volcano_dict_item["fc"]
                save_df["pvalue"] = volcano_dict_item["pvalue"]
                if not os.path.exists(f"{save_path}/volcano/used/"):
                    os.makedirs(f"{save_path}/volcano/used/")
                save_df.to_csv(f"{save_path}/volcano/used/{str(key)}" + ".csv")
