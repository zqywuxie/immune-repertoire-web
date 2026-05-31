import os
import shutil

import pandas as pd
from itertools import combinations
from scipy.stats import mannwhitneyu
import pymongo
from appone.constant import DBURL
from sklearn.preprocessing import MinMaxScaler
scaler = MinMaxScaler()
import seaborn as sns
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import matplotlib.pyplot as plt
import warnings
from typing import Any

warnings.filterwarnings("ignore", category=FutureWarning)
# custom_palette = ["#ccf9e8", "#caffca", "#c8def9", "#ffe0c0", "#ffe0e0","#FFC0E0","#eeccf9","#ece6ca"]
sns.set_palette("pastel")


def function(file: str, projectName: str) -> None:
    """
    计算基因使用的 P 值（显著性），并将结果保存到数据库和 CSV，同时绘制条形图。
    """
    df = pd.read_csv(file)
    df = df.fillna(0)
    categorys = df.Category.unique().tolist()
    cate_cbs = list(combinations(categorys, 2))
    cols = df.columns[2:]
    pvalue_df = pd.DataFrame(columns=cols, index=cate_cbs)

    record_cols = []
    for cb in cate_cbs:
        for col in cols:
            cate_1_values = df[df.Category == cb[0]][col]
            cate_2_values = df[df.Category == cb[1]][col]
            pvalue = mannwhitneyu(cate_1_values, cate_2_values).pvalue
            pvalue_df.at[cb, col] = pvalue
            if pvalue < 0.05:
                if col not in record_cols:
                    record_cols.append(col)
    df_use = df[df.columns[:2].tolist() + record_cols]

    pvalue_df.index.name = "Category"
    pvalue_df = pvalue_df.reset_index()
    Pvalue_path = os.path.split(file)[0] + "/barchart/pvalue/"

    if not os.path.exists(Pvalue_path):
        os.makedirs(Pvalue_path)

    # 把pvalue_df df_use  保存到数据库中
    client = pymongo.MongoClient(DBURL, maxidletimems=120000)
    db = client[projectName]
    project_gene_usage_collection = db[f"{projectName}_gene_usage"]
    group = os.path.basename(os.path.split(file)[0])
    # path = os.path.dirname(file)
    # path = os.path.dirname(path)
    path = os.path.split(os.path.split(file)[0])[0]
    v_or_j_usage = os.path.basename(path)
    # print("v_or_j_usage:", v_or_j_usage)
    # print("group_name:", group)  # lastname
    # print(f"gene: {group} {v_or_j_usage}{df_use.shape[0]}")
    data = {
        "group": group,
        "pvalue_df": pvalue_df.to_dict(orient='list'),
        "type": os.path.split(file)[-1][:-4],
        "v_or_j_usage": v_or_j_usage,
        "df_use": df_use.to_dict(orient='list')
    }
    project_gene_usage_collection.insert_one(data)
    client.close()

    pvalue_df.to_csv(Pvalue_path+os.path.split(file)[-1])

    # from  appone.constant import PROJECT_FILE

    # df_use_path = PROJECT_FILE+ "/"+ projectName+ f"/used/{group}/"
    df_use_path = os.path.split(file)[0] + f"/barchart/used/{group}/"
    if not os.path.exists(df_use_path):
        os.makedirs(df_use_path)
    df_use.to_csv(df_use_path+os.path.basename(file),index=False)

    df_use.index = df_use["sample"]
    df_use.pop("sample")
    if df_use.shape[1] == 1:
        return
    df_normalized = pd.DataFrame(scaler.fit_transform(df_use[df_use.columns[1:]]), columns=df_use.columns[1:],
                                 index=df_use.index)
    df_normalized.insert(loc=0, column="Category", value=df_use["Category"])
    df_all_melt = df_normalized.melt(id_vars="Category", var_name="Gene", value_name="Frequency")
    # df_all_melt = df_all_melt.sort_values(by=["Category","Gene","Frequency"])
    x_len = (df_use.shape[1] - 1) * 1
    # plt.figure(figsize=(x_len, 5))
    # sns.set_style("white")
    # sns.set_palette("pastel")
    if "VJ" not in v_or_j_usage:
        plt.figure(figsize=(x_len, 5))
        # sns.set(rc={'figure.figsize': (x_len, 4.8)})
        sns.set_style("white")
        ax_box = sns.barplot(x="Gene", y="Frequency", hue="Category", data=df_all_melt, errorbar='se', linewidth=3,
                             edgecolor="black", errwidth=3, capsize=0.1, width=0.8)
        ax_box.set_xticklabels(labels=ax_box.get_xticklabels(), rotation=45)
        ax_box.xaxis.set_tick_params(which='both', bottom=True, top=False, direction='out', width=3, length=5)
        ax_box.yaxis.set_tick_params(which='both', bottom=True, top=False, direction='out', width=3, length=5)
        plt.xticks(fontweight='semibold', size=25)  #fontfamily ='Times New Roman'
        plt.yticks(fontweight='semibold', size=25)
        ax_box.spines['bottom'].set_linewidth(4)  #图框下边
        ax_box.spines['left'].set_linewidth(4)  #图框左边
        ax_box.spines['top'].set_visible(False)
        ax_box.spines['right'].set_visible(False)
        ax_box.get_legend().set_visible(True)
        fig_path = os.path.split(file)[0] + "/barchart/Fig/"
        if not os.path.exists(fig_path):
            os.makedirs(fig_path)
        ax_box.get_figure().savefig(fig_path + os.path.split(file)[-1][:-4] + ".png", dpi=300, bbox_inches="tight")
        ax_box.cla()
        plt.close()


# todo process
def start_func(projectName: str) -> None:
    """
    启动所有基因使用频率分析流程。
    """
    from appone.constant import PROJECT_FILE,CHAIN_TYPES
    # PROJECT_FILE = rf"E:/Program Files/PycharmProjects/djangoProject/djangoProject/tools/process_script/{projectName}/gene_usage"
    PROJECT_FILE = PROJECT_FILE + fr"/{projectName}/gene_usage"
    files = []
    for dirname, dirs, filenames in os.walk(PROJECT_FILE + "/usage_cate/usage"):
        for filename in filenames:
            if filename.endswith(".csv") and filename.split(".")[0] in CHAIN_TYPES:
                files.append(os.path.join(dirname, filename))
    # for file in files:
    #     print(file)
    for file in files:
        function(file=file, projectName=projectName)
