import pandas as pd
import numpy as np
from scipy.stats import mannwhitneyu
from itertools import combinations
import seaborn as sns
import os
import matplotlib.pyplot as plt
import re
import copy
import time
import warnings
from typing import Dict, List, Any

warnings.filterwarnings("ignore", category=FutureWarning)
# from pypushdeer import PushDeer

# PushDeerKeylist = ['PDU17616T5qWX3eH5verJ5yzg4wxK33fGAqXhvCJD',"PDU18083TFNlRrsIG2ikE3AXGzF5waLdL7MnLZiW1"]

data_split_point_begin = 1
data_split_point = 2

# file_dir = "usage_cate"

threash_hold_s = 0.01
threash_hold_p = 0.05

remove_list = [0]

# path_list = []
# for root, dirnames, filenames in os.walk(file_dir):
#     for filename in filenames:
#         path_list.append(os.path.join(root, filename))


def get_class_dict(dataframe: pd.DataFrame) -> Dict[str, List[str]]:
    """
    从数据框中提取分类信息并返回分类字典。
    """
    class_dict = {}
    for col_name in dataframe.columns[data_split_point_begin:data_split_point]:
        col_type_list = []
        for arg in dataframe[col_name]:
            if arg not in col_type_list:
                col_type_list.append(arg)
        for remove_item in remove_list:
            if remove_item in col_type_list:
                col_type_list.remove(remove_item)
        class_dict[col_name] = col_type_list
    return class_dict


def pvalue_list_all(df: pd.DataFrame) -> Dict[str, List[Any]]:
    """
    计算数据框中所有特征在不同分类组合下的 P 值。
    """
    # global class_dict
    class_dict = get_class_dict(df)
    p_value_all = {}
    for colname, itemlist in class_dict.items():
        itemlist = sorted(itemlist)
        p_value_all[colname] = []
        combination_list = list(combinations(itemlist, 2))
        for cb in combination_list:
            for param_col in df.columns[data_split_point:]:
                try:
                    pvalue = mannwhitneyu(
                        df[df[colname] == cb[0]][param_col],
                        df[df[colname] == cb[1]][param_col],
                        alternative='two-sided'
                    ).pvalue
                    p_value_all[colname].append((cb[0], cb[1], param_col, pvalue))
                except:
                    continue
    return p_value_all


global_path = "heatmap"


def draw(path: str) -> None:
    """
    根据给定的 CSV 文件路径，计算 P 值并绘制基因使用热图。
    """
    # print("process pid:", os.getpid(), "is runing ", path)
    filepath, suffix = os.path.splitext(path)
    chain_type = os.path.basename(filepath)
    filepath = os.path.dirname(path)
    save_path = os.path.join(filepath, global_path)
    save_path = os.path.join(save_path, chain_type)
    # print(save_path,suffix)
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    df = pd.read_csv(path, )
    df.fillna(0, inplace=True)
    pvalue_all = pvalue_list_all(df)
    heatmap_columns = df.columns[data_split_point:].tolist()
    for i in range(1, len(heatmap_columns)):
        for k in range(0, len(heatmap_columns) - i):
            numbers_pre = re.findall(r'[1-9]+\.?[0-9]*', heatmap_columns[k])
            numbers_pre = np.array(numbers_pre, dtype=np.float16).tolist()
            numbers_behind = re.findall(r'[1-9]+\.?[0-9]*', heatmap_columns[k + 1])
            numbers_behind = np.array(numbers_behind, dtype=np.float16).tolist()
            n1, n2 = len(numbers_pre), len(numbers_behind)
            minlen = np.min(np.array([n1, n2]))
            maxlen_flag = False
            if n1 > minlen:
                maxlen_flag = True
            for j in range(minlen):
                if numbers_pre[j] != numbers_behind[j]:
                    if numbers_pre[j] > numbers_behind[j]:
                        t = heatmap_columns[k]
                        heatmap_columns[k] = heatmap_columns[k + 1]
                        heatmap_columns[k + 1] = t
                    break
                if j == minlen - 1 and maxlen_flag:
                    t = heatmap_columns[k]
                    heatmap_columns[k] = heatmap_columns[k + 1]
                    heatmap_columns[k + 1] = t
    heatmap_columns.insert(0, "category")
    mapdf_dict = dict([(k, []) for k in heatmap_columns])
    for category, p_list in pvalue_all.items():
        pre_mapdict = copy.deepcopy(mapdf_dict)
        for pair in p_list:
            category_vs = pair[0] + " vs. " + pair[1]
            if category_vs not in pre_mapdict["category"]:
                pre_mapdict["category"].append(category_vs)
            if pair[3] > threash_hold_p:
                pre_mapdict[pair[2]].append(0)
                continue
            array1_avg = np.mean(np.array(df[df[category] == pair[0]][pair[2]], dtype=np.float16))
            array2_avg = np.mean(np.array(df[df[category] == pair[1]][pair[2]], dtype=np.float16))
            if array1_avg > array2_avg:
                if pair[3] < threash_hold_s:
                    pre_mapdict[pair[2]].append(10)
                else:
                    pre_mapdict[pair[2]].append(5)
            else:
                if pair[3] < threash_hold_s:
                    pre_mapdict[pair[2]].append(-10)
                else:
                    pre_mapdict[pair[2]].append(-5)
        pre_df = pd.DataFrame(pre_mapdict, index=pre_mapdict["category"])
        pre_df.drop(columns=["category"], inplace=True)
        heat_y = pre_df.shape[0]
        heat_x = pre_df.shape[1]
        if heat_x > 30:
            num_split = heat_x // 30 + 1
            for i in range(num_split):
                if i == num_split - 1:
                    iso_df = pre_df[pre_df.columns[i * 30:]]
                else:
                    iso_df = pre_df[pre_df.columns[i * 30:(i + 1) * 30]]
                pre_x = len(iso_df.columns)
                plt.subplots(figsize=(pre_x, heat_y), dpi=120)
                #         sns.heatmap(iso_df,cbar=True,linewidths=0.5,square=True,mask=iso_df.values==0,cmap="coolwarm")
                sns.heatmap(iso_df, cbar=False, linewidths=0.5, square=True, cmap="coolwarm", vmax=10, vmin=-10, )
                plt.ylim(0, heat_y)
                plt.xlim(0, pre_x)
                plt.yticks(rotation=0)
                ax = plt.gca()
                ax.spines["top"].set_visible(True)
                ax.spines["bottom"].set_visible(True)
                ax.spines["left"].set_visible(True)
                ax.spines["right"].set_visible(True)
                plt.savefig(save_path + "/" + category + "_" + str(i) + ".jpg", bbox_inches='tight')
                plt.clf()
                plt.close()
        else:
            pre_x = len(pre_df.columns)
            plt.subplots(figsize=(pre_x, heat_y), dpi=120)
            #         sns.heatmap(iso_df,cbar=True,linewidths=0.5,square=True,mask=iso_df.values==0,cmap="coolwarm")
            sns.heatmap(pre_df, cbar=False, linewidths=0.5, square=True, cmap="coolwarm", vmax=10, vmin=-10, )
            plt.ylim(0, heat_y)
            plt.xlim(0, pre_x)
            plt.yticks(rotation=0)
            ax = plt.gca()
            ax.spines["top"].set_visible(True)
            ax.spines["bottom"].set_visible(True)
            ax.spines["left"].set_visible(True)
            ax.spines["right"].set_visible(True)
            plt.savefig(save_path + "/" + category + ".jpg", bbox_inches='tight')
            plt.clf()
            plt.close()

        csv_savepath = os.path.join(save_path, "csv_file")
        if not os.path.exists(csv_savepath):
            os.makedirs(csv_savepath)
        csv_savepath = os.path.join(csv_savepath, category)
        pre_df.to_csv(csv_savepath + suffix)
        #  todo save
    # print("process pid:", os.getpid(), "have run ", path)


from concurrent.futures import *
from multiprocessing import cpu_count

core_num = cpu_count()


def start_func(projectName: str) -> None:
    """
    启动并行化的基因使用热图绘制流程。
    """
    from appone.constant import PROJECT_FILE,CHAIN_TYPES
    file_dir = PROJECT_FILE + fr"/{projectName}/gene_usage/usage_cate"
    path_list = []
    for root, dirnames, filenames in os.walk(file_dir):
        for filename in filenames:
            if filename.endswith(".csv") and filename.split(".")[0] in CHAIN_TYPES:
                path_list.append(os.path.join(root, filename))

    print(path_list[0])
    with ProcessPoolExecutor(max_workers=core_num) as executor:
        results = executor.map(draw, path_list)

# if __name__ == '__main__':
#     from appone.constant import PROJECT_FILE
#     aaa =  r"./static/files"
#     file_dir = aaa + fr"/mou/gene_usage/usage_cate"
#     path = "./"
#     path_list = []
#     for root, dirnames, filenames in os.walk(file_dir):
#         for filename in filenames:
#             path_list.append(os.path.join(root, filename))
#
#     print(path_list)-