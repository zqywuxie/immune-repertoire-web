import pandas as pd
from scipy.stats import mannwhitneyu
from itertools import combinations
import seaborn as sns
import os
import numpy as np
import matplotlib.pyplot as plt
from itertools import combinations
from sklearn.preprocessing import StandardScaler
import umap
from copy import deepcopy
import pymongo
from appone.constant import DBURL
from djangoProject.tools.logger import log
from typing import List, Dict, Tuple, Any, Optional

logger = log.GetLogger().get_logger()
"""
file_dir can be a filename or a dirname
"""
file_dir = "Datapoint"

"""
if filename_or_file = 1, input is an dirname
if filename_or_file = 0, input will be an filename
"""
filename_or_file = 1

"""
the threshold of p_value, if smaller than the thresh,the data can be in calculating and plot the boxes.
"""
threshold_pvalue = 0.05

"""
Find the combination in class, the data_split_point_begin is the beginning postion 
but it not contain the number positon, eg. if data_split_point_begin = "Group1", data_split_point = "Group2",
which contains column 2 to 9.
"""
# data_split_point_begin = "category"
# data_split_point_over = "category"
"""
Which decide the parameters count into calculate, including the param name
"""
# param_begin = "IGHA_percent_by_clone"
# param_over = "CD11a_H_dT_20171114"

"""
Remove the sepcified type in dataframe
"""
remove_list = []

"""
Specify the boxplot bar type as multiple or pair
if pair_or_mutiple = 1, plot the mutiple index umap
if pair_or_mutiple = 0, just the pair index umap
"""
pair_or_mutiple = 1

"""
min_distance which define the min distance of the two point
n_neighbors defines the cluster number of point
"""
umap_n_neighbors = 6
umap_min_dist = 0.01


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
    移除指定的数据子集（当前直接返回原数据框）。
    """
    return dataframe


def get_class_dict(dataframe: pd.DataFrame, data_split_point_begin: str, data_split_point_over: str) -> Dict[str, List[str]]:
    """
    从数据框中提取分类字典。
    """
    begin = dataframe.columns.tolist().index(data_split_point_begin)
    over = dataframe.columns.tolist().index(data_split_point_over) + 1
    class_dict = {}
    for col_name in dataframe.columns[begin:over]:
        col_type_list = []
        for arg in dataframe[col_name]:
            if arg not in col_type_list:
                col_type_list.append(arg)
        for remove_item in remove_list:
            if remove_item in col_type_list:
                col_type_list.remove(remove_item)
        class_dict[col_name] = col_type_list
    return class_dict


def pvalue_list_all(df: pd.DataFrame, data_split_point_begin: str, data_split_point_over: str, param_begin: str, param_over: str) -> Tuple[Dict[str, List[Tuple[str, str, str, float]]], Dict[str, List[str]]]:
    """
    计算所有参数在不同分类组合下的 P 值。
    """
    # global class_dict
    param_begin_position = df.columns.tolist().index(param_begin)
    param_over_position = df.columns.tolist().index(param_over) + 1
    class_dict = get_class_dict(df, data_split_point_begin, data_split_point_over)
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
                        alternative='two-sided'
                    ).pvalue
                    p_value_all[colname].append((cb[0], cb[1], param_col, pvalue))
                except:
                    continue
    return p_value_all, class_dict


def find_cateToparam(p_value_all: Dict[str, List[Tuple[str, str, str, float]]], class_dict: Dict[str, List[str]]) -> Tuple[Dict[str, Dict[Tuple[str, str], Dict[str, float]]], Dict[str, Dict[Tuple[str, ...], List[str]]], Dict[str, Dict[Tuple[str, ...], List[Tuple[str, str, str, float]]]]]:
    """
    寻找 P 值显著的特征并按分类进行整理。
    """
    pair_dict = {}
    all_dict = {}
    all_dict_Pvalue = {}
    for category, pvalue_tuples_list in p_value_all.items():
        pair_dict[category] = {}
        all_dict[category] = {}
        all_dict_Pvalue[category] = {}
        cb_list = []
        if len(class_dict[category]) >= 3:
            for i in range(len(class_dict[category]) + 1)[2:]:  # 改成2
                cb_list = cb_list + list(combinations(class_dict[category], i))
        else:
            cb_list = list(combinations(class_dict[category], 2))
        for pvalue_tuple in pvalue_tuples_list:
            pair_tuple = (pvalue_tuple[0], pvalue_tuple[1])
            if pvalue_tuple[3] <= threshold_pvalue:
                if pair_tuple not in pair_dict[category].keys():
                    pair_dict[category][pair_tuple] = {pvalue_tuple[2]: pvalue_tuple[3]}
                else:
                    pair_dict[category][pair_tuple][pvalue_tuple[2]] = pvalue_tuple[3]
                for cb in cb_list:
                    if pvalue_tuple[0] in cb and pvalue_tuple[1] in cb:
                        if cb not in all_dict[category].keys():
                            all_dict[category][cb] = [pvalue_tuple[2]]
                            all_dict_Pvalue[category][cb] = [pvalue_tuple]
                            continue
                        if pvalue_tuple[2] not in all_dict[category][cb]:
                            all_dict[category][cb].append(pvalue_tuple[2])
                        all_dict_Pvalue[category][cb].append(pvalue_tuple)
        temporary_dict = deepcopy(all_dict_Pvalue[category])
        for cb, tuple_params_list in temporary_dict.items():
            params = []
            for pvalue_tuple in tuple_params_list:
                if pvalue_tuple[0] not in params:
                    params.append(pvalue_tuple[0])
                if pvalue_tuple[1] not in params:
                    params.append(pvalue_tuple[1])
            if len(params) != len(cb):
                del (all_dict_Pvalue[category][cb])
                del (all_dict[category][cb])
        del temporary_dict
        # pair_dict[category]
        if len(pair_dict[category].keys()) == 0:
            del pair_dict[category]
        if len(all_dict[category].keys()) == 0:
            del all_dict[category]
        if len(all_dict_Pvalue[category].keys()) == 0:
            del all_dict_Pvalue[category]
    return pair_dict, all_dict, all_dict_Pvalue


def replacedot(name: str) -> str:
    """
    替换名称中的逗号和空格，用于生成文件名。
    """
    name = name.replace(",", "")
    name = name.replace(" ", " vs. ")
    name = name.replace("'", "")
    return name


def draw_umap_all(dataframe: pd.DataFrame, all_dict: Dict[str, Dict[Tuple[str, ...], List[str]]], all_dict_Pvalue: Dict[str, Dict[Tuple[str, ...], List[Tuple[str, str, str, float]]]], file_name: str, root_path: str, projectName: str) -> None:
    """
    绘制并保存所有显著特征组合的 UMAP 降维图，并将结果存入数据库。
    """
    for category, map_dict in all_dict.items():
        for type_tuple, params in map_dict.items():
            MinCategory_Num = umap_n_neighbors
            types = dataframe[dataframe[category].isin(type_tuple)][category].unique().tolist()
            for type_name in types:
                num = dataframe[dataframe[category] == type_name].shape[0]
                if num < MinCategory_Num:
                    MinCategory_Num = num
            if MinCategory_Num <= 1:
                logger.info(f"{category}的{types}中有的行数为{MinCategory_Num},小于等于1，{category}的{types}umap跳过")
                # print(f"{category}的{types}中有的行数为{MinCategory_Num},小于等于1，{category}的{types}umap跳过")
                continue
            print(f"{category}的{types}中有的行数为{MinCategory_Num}")
            umap_n_neighbors_local = umap_n_neighbors
            if MinCategory_Num < umap_n_neighbors:
                umap_n_neighbors_local = MinCategory_Num
            type_list = list(type_tuple)
            use_df = pd.DataFrame(columns=dataframe.columns)
            for ctype in type_list:
                use_df = use_df.append(dataframe[dataframe[category] == ctype])
            map_str = "use_df." + category + ".map"
            map_dic = {}
            for iostype, i in zip(type_list, range(len(type_list))):
                map_dic[iostype] = i
            try:
                color_class_list = [[x] for x in eval(map_str + '(' + str(map_dic) + ')')]
                bio_data = use_df[params].values
                scaled_bio_data = StandardScaler().fit_transform(bio_data)
                reducer = umap.UMAP(n_neighbors=umap_n_neighbors_local, min_dist=umap_min_dist, n_epochs=50,
                                    random_state=40)
                embedding = reducer.fit_transform(scaled_bio_data)
            except Exception as e:
                print(type_tuple, params, "出现问题", e)
                logger.error(f"{tuple}, {params},出现问题，{str(e)}")

            plt.figure(figsize=(5, 4.8))
            scatter = plt.scatter(
                embedding[:, 0],
                embedding[:, 1],
                c=color_class_list)
            bbox_props = dict(boxstyle="round", fc="w", ec="0.5", alpha=0.6)
            lenged_text = ""
            for Pvalue_tuple in all_dict_Pvalue[category][type_tuple]:
                lenged_text = lenged_text + Pvalue_tuple[0] + " vs. " + Pvalue_tuple[1] + " On " + Pvalue_tuple[
                    2] + " : " + str(float('%.4g' % Pvalue_tuple[3])) + "\n"

            ax = plt.gca()
            plt.text(1.02, 0, lenged_text[:-1], backgroundcolor="black", bbox=bbox_props, rotation=0,
                     transform=ax.transAxes)
            plt.legend(handles=scatter.legend_elements()[0], labels=type_list, title="category")
            plt.gca().set_aspect('equal', 'datalim')
            name = str(type_tuple).replace("(", "")
            name = name.replace(")", "")
            name = replacedot(name)
            # print(f"name:{name}")
            plt.title('UMAP of ' + name + " in " + category, fontsize=12)
            figure_path = os.path.join(root_path, file_name)  # ?
            # print(f"figure_path:{figure_path}")
            if not os.path.exists(figure_path):
                os.makedirs(figure_path)
            plt.savefig(figure_path + "/" + name + ".png", bbox_inches='tight', dpi=300)
            plt.clf()

            params.insert(0, category)
            save_df = use_df[params]

            csv_files = os.path.join(root_path,category, "csv_file")
            if not os.path.exists(csv_files):
                os.makedirs(csv_files)
            save_df.to_csv(csv_files + "/" + name + ".csv")
            try:
                client = pymongo.MongoClient(DBURL, maxidletimems=120000)
                db = client[projectName]
                umap_collection = db[projectName + "_umap"]
                data = {
                    "name": name,
                    "df_use": save_df.to_dict(orient='list'),
                    "group": category,
                }
                umap_collection.insert_one(data)
            except Exception as e:
                print(f"存{projectName}的umap数据出现错误了：{e}")
                logger.info(f"存{projectName}的umap数据出现错误了：{e}")
            finally:
                client.close()
                plt.close()


# def draw(data_path,data_split_point_begin):
#     filepath, filename = os.path.split(data_path)
#     stem, suffix = os.path.splitext(filename)
#     df = pd.read_csv(data_path, index_col=0)
#     df.fillna(0, inplace=True)
#     p_value_all = pvalue_list_all(df,data_split_point_begin)
#     pair_dict, all_dict, all_dict_Pvalue = find_cateToparam(p_value_all)
#     draw_umap_all(dataframe=df, all_dict=all_dict, all_dict_Pvalue=all_dict_Pvalue, file_name=stem,
#                   root_path="umap_all")


# from concurrent.futures import *
# from multiprocessing import cpu_count


# core_num = cpu_count()

# if __name__ == '__main__':
#     Csv_path = get_filesdir(file_dir)
#     with ProcessPoolExecutor(max_workers=core_num) as executor:
#         results = executor.map(draw,Csv_path)


# for data_path in get_filesdir(file_dir):
#     filepath, filename = os.path.split(data_path)
#     stem, suffix = os.path.splitext(filename)
#     db = pd.read_csv(data_path,index_col=0)
#     db.fillna(0,inplace=True)
#     p_value_all = pvalue_list_all(db)
#     pair_dict,all_dict,all_dict_Pvalue = find_cateToparam(p_value_all)
#     draw_umap_all(dataframe=db,all_dict=all_dict,all_dict_Pvalue=all_dict_Pvalue,file_name=stem,root_path="umap_all")
def process_mid(all_dict_Pvalue_list: List[Tuple[str, str, str, float]]) -> List[Tuple[str, str, str, float]]:
    """
    中间处理函数，根据特征类型对 P 值列表进行分组处理。
    """
    to_process_dict = {}
    for ele in all_dict_Pvalue_list:
        if str(ele[0]) + str(ele[1]) not in to_process_dict:
            to_process_dict[str(ele[0]) + str(ele[1])] = [ele]
        else:
            to_process_dict[str(ele[0]) + str(ele[1])].append(ele)
    return_list = []
    for key, value in to_process_dict.items():
        return_list = return_list + process_all_dict_Pvalue_list(value)
    return return_list


def process_all_dict_Pvalue_list(all_dict_Pvalue_list: List[Tuple[str, str, str, float]]) -> List[Tuple[str, str, str, float]]:
    """
    对 P 值列表进行过滤和排序，限制各类型特征的数量。
    """
    # V_LIST = ["TRBV","TRAV","TRGV","TRDV","IGHV","IGKV","IGLV"]
    # J_LIST = ["IGHJ","IGKJ","IGLJ","TRBJ","TRAJ","TRGJ","TRDJ"]
    profile_list = []
    list_1J = []
    list_1V = []
    list_1VJ = []
    for element in all_dict_Pvalue_list:
        if "J" in element[2] and "V" not in element[2]:
            list_1J.append(element)
            continue
        elif "V" in element[2] and "J" not in element[2]:
            list_1V.append(element)
            continue
        elif "V" in element[2] and "J" in element[2]:
            list_1VJ.append(element)
            continue
        else:
            profile_list.append(element)
    profile_list = sorted(profile_list, key=lambda x: x[3], reverse=False)
    list_1J = sorted(list_1J, key=lambda x: x[3], reverse=False)
    list_1V = sorted(list_1V, key=lambda x: x[3], reverse=False)
    list_1VJ = sorted(list_1VJ, key=lambda x: x[3], reverse=False)
    if len(profile_list) > 7:
        profile_list = profile_list[0:7]
    if len(list_1V) > 5:
        list_1V = list_1V[0:5]
    if len(list_1J) > 3:
        list_1J = list_1J[0:3]
    if len(list_1VJ) > 5:
        list_1VJ = list_1VJ[0:5]
    return profile_list + list_1V + list_1J + list_1VJ


def process_all_dict_Pvalue(all_dict_Pvalue: Dict[str, Dict[Tuple[str, ...], List[Tuple[str, str, str, float]]]]) -> Dict[str, Dict[Tuple[str, ...], List[Tuple[str, str, str, float]]]]:
    """
    处理 P 值字典，对其中的列表进行过滤处理。
    """
    for key in all_dict_Pvalue:
        all_dict_Pvalue = all_dict_Pvalue[key]
        for category, all_dict_Pvalue_list in all_dict_Pvalue.items():
            all_dict_Pvalue_list = process_mid(all_dict_Pvalue_list)
            all_dict_Pvalue[category] = all_dict_Pvalue_list
    return_dict = {key: all_dict_Pvalue}
    return return_dict


def start_func(df: pd.DataFrame, projectName: str, data_split_point_begin2: str, param_begin2: str, param_over2: str) -> None:
    """
    启动 UMAP 分析流程。
    """
    from appone.constant import PROJECT_FILE
    PROJECT_FILE = PROJECT_FILE + fr"/{projectName}/umap_all"
    # PROJECT_FILE = rf"E:/Program Files/PycharmProjects/djangoProject/djangoProject/tools/process_script/{projectName}/umap_all"
    # global data_split_point_begin, data_split_point_over, param_begin, param_over
    # data_split_point_begin = data_split_point_over = data_split_point_begin2
    # param_begin = param_begin2
    # param_over = param_over2
    df.fillna(0, inplace=True)
    p_value_all, class_dict = pvalue_list_all(df, data_split_point_begin2, data_split_point_begin2, param_begin2,
                                              param_over2)
    pair_dict, all_dict, all_dict_Pvalue = find_cateToparam(p_value_all, class_dict)
    # 处理all_dict_Pvalue 让每一组中，v5,j3,vj5,profile7,一共20个参数
    all_dict_Pvalue = process_all_dict_Pvalue(all_dict_Pvalue)
    draw_umap_all(dataframe=df, all_dict=all_dict, all_dict_Pvalue=all_dict_Pvalue, file_name=data_split_point_begin2,
                  root_path=PROJECT_FILE, projectName=projectName)
