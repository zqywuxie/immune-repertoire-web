# -*- coding: utf-8 -*-
import pandas as pd
from scipy.stats import mannwhitneyu
from itertools import combinations
import seaborn as sns
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pymongo
from appone.constant import DBURL
from appone.constant import PROJECT_FILE
import warnings
from typing import List, Dict, Tuple, Any, Optional

warnings.filterwarnings("ignore", category=FutureWarning)
# PROJECT_FILE = r"E:/Program Files/PycharmProjects/djangoProject/djangoProject/tools/process_script"
"""
file_dir can be a filename or a dirname
"""
file_dir = "Datapoint"

"""
if filename_or_file = 1, input is a dirname
if filename_or_file = 0, input will be a filename
"""
filename_or_file = 1

"""
the threshold of p_value, if smaller than the thresh,the data can be in calculating and plot the boxes.
"""
threshold_pvalue = 1

"""
Find the combination in class, the data_split_point_begin is the beginning postion 
but it not contain the number positon, eg. if data_split_point_begin = "Group1", data_split_point = "Group2",
"""
# data_split_point_begin = "all"
# data_split_point_over = "baseline"

"""
Which decide the parameters count into calculate, including the param name
"""

# param_begin = "TRA_percent_reads_all"
# param_over = "TRB_mean_cdr3_length"

"""
Remove the sepcified type in dataframe
"""
remove_list = [0]

"""
Specify the boxplot bar type as multiple or pair
if box_bar_mutiple = 1, plot the mutiple bar box
if box_bar_mutiple = 0, just the pair
"""
box_bar_mutiple = 1

"""
BoxPlot will arrange by the dict 
"""


# arrange_dict = {"Group":["Group1","Group2","Group3"]}


def get_filesdir(file_dir: str) -> List[str]:
    """
    获取指定目录下的所有文件路径列表。
    """
    if filename_or_file == 0:
        return [file_dir]
    if filename_or_file == 1:
        path_list = []
        for root, dirnames, filenames in os.walk(file_dir):
            for filename in filenames:
                path_list.append(os.path.join(root, filename))
        return path_list


def get_removed_subdf(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    从数据框中移除指定的子集（当前实现直接返回原数据框）。
    """
    return dataframe


def get_class_dict(dataframe: pd.DataFrame, arrange_dict: Dict[str, List[str]], data_split_point_begin: str, data_split_point_over: str) -> Dict[str, List[str]]:
    """
    获取分类字典，结构为 {"列名": [分类值1, 分类值2]}。
    """
    begin = dataframe.columns.tolist().index(data_split_point_begin)
    over = dataframe.columns.tolist().index(data_split_point_over) + 1
    class_dict = {}
    for col_name in dataframe.columns[begin:over]:
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


def pvalue_list_all(df: pd.DataFrame, arrange_dict: Dict[str, List[str]], data_split_point_begin: str, data_split_point_over: str, param_begin: str, param_over: str) -> Tuple[Dict[str, List[Tuple[str, str, str, float]]], Dict[str, List[str]]]:
    """
    计算所有参数在不同分类组合下的 P 值（Mann-Whitney U 检验）。
    """
    param_begin_position = df.columns.tolist().index(param_begin)
    param_over_position = df.columns.tolist().index(param_over) + 1
    # global class_dict
    class_dict = get_class_dict(df,arrange_dict,data_split_point_begin,data_split_point_over)
    p_value_all = {}
    for colname, itemlist in class_dict.items():
        p_value_all[colname] = []
        combination_list = list(combinations(itemlist, 2))
        for cb in combination_list:
            for param_col in df.columns[param_begin_position:param_over_position]:
                try:
                    pvalue = mannwhitneyu(
                        df[df[colname] == cb[0]][param_col],
                        df[df[colname] == cb[1]][param_col],
                        alternative= 'two-sided'
                    ).pvalue
                    p_value_all[colname].append((cb[0], cb[1], param_col, pvalue))
                except:
                    continue
    return p_value_all,class_dict


def find_tcp(p_value_all: Dict[str, List[Tuple[str, str, str, float]]], class_dict: Dict[str, List[str]]) -> Tuple[Dict[str, Dict[str, List[str]]], Dict[str, Dict[str, List[Tuple[str, str, float]]]]]:
    """
    寻找 P 值小于阈值的显著差异组合。
    """
    in_indice_dict = {}
    pvalue_useful_dict = {}
    for class_col, col_items in class_dict.items():
        pvalue_useful_dict[class_col] = {}
        for pair in p_value_all[class_col]:
            if pair[3] > threshold_pvalue:
                continue
            if pair[2] not in pvalue_useful_dict[class_col]:
                pvalue_useful_dict[class_col][pair[2]] = [(pair[0], pair[1], pair[3])]
            else:
                pvalue_useful_dict[class_col][pair[2]].append((pair[0], pair[1], pair[3]))
            if class_col not in in_indice_dict.keys():
                in_indice_dict[class_col] = {pair[2]: [pair[0], pair[1]]}
            elif pair[2] not in in_indice_dict[class_col].keys():
                in_indice_dict[class_col][pair[2]] = [pair[0], pair[1]]
            else:
                for item in pair[:2]:
                    if item not in in_indice_dict[class_col][pair[2]]:
                        in_indice_dict[class_col][pair[2]].append(item)
    return in_indice_dict, pvalue_useful_dict


def plotboxs_mat_mutiple(df: pd.DataFrame, pvalue_list: List[Tuple[str, str, float]], class_col: str, param: str, filename: str,
                         pvalue_pair_dict: Dict[str, Any], map_list: List[str], PROFILE_BOXPLOT_DIRNAME: str, class_dict: Dict[str, List[str]]) -> None:
    """
    绘制并保存箱线图。
    """
    plot_df = df[["sample", class_col, param]]
    concat_df = pd.DataFrame({"sample": [], class_col: [], param: []})
    for col_type in class_dict[class_col]:

        concat_df = pd.concat([concat_df, plot_df[plot_df[class_col] == col_type]])
    sns.set(rc={'figure.figsize': (0.8 * len(class_dict[class_col]), 4.8)})
    # llll = len(class_dict[class_col])
    # print(llll,f"长度为 。。。。。{PROFILE_BOXPLOT_DIRNAME}  {class_col}")
    sns.set_style("white")
    sns.set_palette("pastel")
    # sns.despine()
    ax_point = sns.stripplot(y=param, x=class_col, data=concat_df, color="purple", jitter=True)
    # print(class_col,param,concat_df)
    try:
        ax_box = sns.boxplot(y=param, x=class_col, data=concat_df, linewidth=2, width=0.6)
    except Exception as e :
        print(e,param,class_col,concat_df.columns)
    bbox_props = dict(boxstyle="round", fc="w", ec="0.5", alpha=0.6)
    lenged_text = ""
    for ppair_value in pvalue_list:
        vs_str = ppair_value[0] + " VS " + ppair_value[1]
        if vs_str not in map_list:
            map_list.append(vs_str)
        lenged_text = lenged_text + ppair_value[0] + " VS " + ppair_value[1] + " pvalue:" + str(
            float('%.4g' % ppair_value[2])) + "\n"
        if vs_str not in pvalue_pair_dict["cate"]:
            pvalue_pair_dict["cate"].append(ppair_value[0] + " VS " + ppair_value[1])
        if param not in pvalue_pair_dict.keys():
            pvalue_pair_dict[param] = [(map_list.index(vs_str), float('%.4g' % ppair_value[2]))]
        else:
            pvalue_pair_dict[param].append((map_list.index(vs_str), float('%.4g' % ppair_value[2])))
    font = {
        #     'family':'Times New Roman',
        #      'style':'italic',
        'weight': 'semibold',
        #       'color':'black',
        'size': 16}
    ax_box.set_ylabel(param, fontsize=16, fontdict=font, labelpad=10)
    ax_box.set_xlabel(class_col, fontsize=24, fontdict=font, labelpad=10)
    ax_box.set_xticklabels(labels=ax_box.get_xticklabels(), rotation=45)
    ax_box.tick_params(labelsize=14, length=0)
    plt.xticks(fontweight='semibold', size=14)  #fontfamily ='Times New Roman'
    plt.yticks(fontweight='semibold', size=14)
    ax_box.text(0, 1, lenged_text[:-1], backgroundcolor="black", bbox=bbox_props, transform=ax_box.transAxes,
                rotation=0)
    path = os.path.join(PROJECT_FILE, filename,"boxplot", PROFILE_BOXPLOT_DIRNAME)# PROFILE_BOXPLOT_DIRNAME  "boxplot"
    if not os.path.exists(path):
        os.makedirs(path)
    path = os.path.join(path, class_col)
    if not os.path.exists(path):
        os.mkdir(path)
    fig_path = os.path.join(path, param)
    ax_box.figure.savefig(fig_path, bbox_inches='tight', dpi=400)
    ax_box.cla()
    plt.close()

    csv_path = PROJECT_FILE+f"/{filename}/boxplot/{PROFILE_BOXPLOT_DIRNAME}/{class_col}/used"
    if not os.path.exists(csv_path):
        # os.mkdir(csv_path)
        os.makedirs(csv_path, exist_ok=True)
    concat_df.to_csv(csv_path + "/" + param + ".csv", index=False)

    # csv_path = os.path.join(path, "csvfile") df_use
    # if not os.path.exists(csv_path):
    #     os.mkdir(csv_path)
    # concat_df.to_csv(csv_path + "/" + param + ".csv", index=False)


# if not os.path.exists("boxplot"):
#     os.mkdir("boxplot")


def draw(df: pd.DataFrame, projectName: str, PROFILE_BOXPLOT_DIRNAME: str,
         arrange_dict: Dict[str, List[str]], data_split_point_begin: str, data_split_point_over: str, is_p_value_flag: bool, param_begin: str, param_over: str) -> None:
    """
    主绘图函数：计算 P 值并调用绘图函数生成箱线图，最后将 P 值存入数据库。
    """
    # filepath, filename = os.path.split(data_path)
    # stem, suffix = os.path.splitext(filename)
    filename = projectName
    stem = projectName
    df = df
    df.fillna(0, inplace=True)
    p_value_all,class_dict = pvalue_list_all(df,arrange_dict,data_split_point_begin,data_split_point_over,param_begin,param_over)
    in_indice_dict, pvalue_useful_dict = find_tcp(p_value_all,class_dict)
    for class_col, col_item_dict in in_indice_dict.items():
        pvalue_pair_dict = {"cate": [], }
        map_list = []
        for param, col_types in col_item_dict.items():
            pvalue_list = pvalue_useful_dict[class_col][param]
            # print("boxplot组",class_col, param, col_types, pvalue_list)
            plotboxs_mat_mutiple(df, pvalue_list, class_col, param, stem, pvalue_pair_dict, map_list,PROFILE_BOXPLOT_DIRNAME,class_dict)
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

        df_p_dict = df_p.to_dict(orient="list")
        collection_name = filename + "_boxplot_pvalue"
        try:
            client = pymongo.MongoClient(DBURL, maxidletimems=120000)
            db = client[projectName]
            collection_name = db[collection_name]

            data = {
                    "group": class_col,
                    "p_value": df_p_dict,
                    "category":str(PROFILE_BOXPLOT_DIRNAME)
                }

            collection_name.insert_one(data)

        except Exception as e:
            print(f"{projectName},{PROFILE_BOXPLOT_DIRNAME} boxplot 存pvalue数据出现错误了：{e}")
        finally:
            client.close()
        # sample_collection.insert_many(data_dict)
        df_p_save_path = PROJECT_FILE + f"/{projectName}/boxplot/{PROFILE_BOXPLOT_DIRNAME}/{class_col}/p_value/"
        if not os.path.exists(df_p_save_path):
            os.makedirs(df_p_save_path, exist_ok=True)
        df_p.to_csv(df_p_save_path + f"{class_col}_pvalue" + ".csv", index=False)
        # df_p.to_csv(filename + "_" + class_col + ".csv", index=False)




def start_func(df: pd.DataFrame, arrange_dict2: Dict[str, List[str]], projectName: str,
               data_split_point_begin2: str, data_split_point_over2: str, is_p_value_flag2: bool, PROFILE_BOXPLOT_DIRNAME: str,
               param_begin2: str, param_over2: str) -> None:
    """
    启动箱线图分析流程。
    """
    # print(arrange_dict2,df.columns.tolist())
    draw(df, projectName,PROFILE_BOXPLOT_DIRNAME,
         arrange_dict2,data_split_point_begin2,data_split_point_over2,is_p_value_flag2,param_begin2,param_over2)

    # global arrange_dict
    # global data_split_point_begin
    # global data_split_point_over
    # global is_p_value_flag
    # is_p_value_flag = is_p_value_flag2
    # arrange_dict = arrange_dict2
    # data_split_point_begin = data_split_point_begin2
    # data_split_point_over = data_split_point_over2
    # global param_begin, param_over;
    # param_begin = param_begin2; param_over = param_over2;

# for data_path in  get_filesdir(file_dir):
#     draw(data_path)

# from concurrent.futures import *
# from multiprocessing import cpu_count


# core_num = cpu_count()

# if __name__ == '__main__':
#     Csv_path = get_filesdir(file_dir)
#     with ProcessPoolExecutor(max_workers=core_num) as executor:
#         results = executor.map(draw,Csv_path)
