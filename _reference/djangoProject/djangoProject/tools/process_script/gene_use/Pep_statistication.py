import pandas as pd
import os
import numpy as np
from itertools import combinations
import copy
from appone.constant import PROJECT_FILE
import warnings
from typing import List, Any

warnings.filterwarnings("ignore", category=FutureWarning)


def get_Csv_path(projectName: str) -> List[str]:
    """
    获取指定项目下所有肽段共享数据的 CSV 文件路径。
    """
    # "./Pep_shared_cate"
    file_path = PROJECT_FILE + f"/{projectName}/gene_usage/Pep_shared_cate"
    Csv_path = []
    for root, path, filenames in os.walk(file_path):
        for filename in filenames:
            Csv_path.append(os.path.join(root, filename))
    return Csv_path


def arrage(data_list: List[Any]) -> None:
    """
    整理肽段共享数据，计算各分组间的共享比例并保存结果。
    """
    file_path = data_list[0]
    group = os.path.basename(os.path.dirname(file_path))
    projectName = data_list[1]
    df = pd.read_csv(file_path, low_memory=False)
    df.fillna(0, inplace=True)
    category_dict = {}
    for cate, idname in zip(df.iloc[0].tolist()[1:], df.iloc[0].index[1:].to_list()):
        if cate not in category_dict.keys():
            category_dict[cate] = [idname]
        else:
            category_dict[cate].append(idname)
    df_nocate = df.drop(labels=0, axis=0)
    for cate, idnames in category_dict.items():
        ca = np.array(df_nocate[idnames].values, dtype=np.float32).astype(np.int32)
        df[cate + "__sum"] = [" "] + ca.sum(axis=1).tolist()
        ca[ca >= 1] = 1
        df[cate + "__count"] = [" "] + ca.sum(axis=1).tolist()
    count_name_list = []
    threash_count = 5
    for column in df.columns.to_list():
        if column.find("count") != -1:
            count_name_list.append(column)
    all_num = np.sum(np.array(df[count_name_list].iloc[1:].values, dtype=np.float32).astype(np.int32), axis=1).tolist()
    all_num.insert(0, " ")
    df["all_num"] = all_num
    df_sort = df.iloc[1:].sort_values(by="all_num", axis=0, ascending=False, inplace=False, kind='quicksort',
                                      na_position='last')
    df_sort = df_sort[df_sort["all_num"] > threash_count]
    cb_list = []
    category_list = []
    for i in range(len(count_name_list) + 1)[2:]:
        cb_list += list(combinations(count_name_list, i))
    cb_list = count_name_list + cb_list
    # cb_list = cb_list[:-1]
    proportion_dict = {}
    df_t = pd.DataFrame(columns=df_sort.columns)
    for cb in cb_list:
        other_list = copy.deepcopy(count_name_list)
        if type(cb) == str:
            other_list.remove(cb)
            df_m = df_sort[df_sort[cb] != 0]
            for remove_type in other_list:
                df_m = df_m[df_m[remove_type] == 0]  # 在本分组只要有一个sample表达，而在其他分组中没有表达
            pre_num = df_m.shape[0]
            proportion_dict[cb] = pre_num
            category_list += pre_num * [cb]
            df_t = pd.concat([df_t, df_m])
            continue
        df_m = df_sort
        for item in cb:
            other_list.remove(item)
        for item in cb:
            df_m = df_m[df_m[item] != 0]
        for item in other_list:
            df_m = df_m[df_m[item] == 0]
        pre_num = df_m.shape[0]
        proportion_dict[cb] = pre_num
        category_list += pre_num * [cb]
        df_t = pd.concat(
            [df_t, df_m])
    df_t["category"] = category_list
    df_top = pd.DataFrame(df.iloc[0]).T
    df_top["category"] = " "
    df_t = pd.concat([df_top, df_t])
    arrage_path = PROJECT_FILE + f"/{projectName}/cdr3_share/arrage_pep"  #"arrage_pep"
    dir = os.path.split(file_path)
    save_path = arrage_path + f"/{group}"
    mkidrs(save_path)
    df_t.to_csv(os.path.join(save_path, dir[1]), index=False)
    sum_value = 0
    for key, value in proportion_dict.items():
        sum_value += value
    for key, value in proportion_dict.items():
        if sum_value == 0:
            proportion_dict[key] = 0
        else:
            proportion_dict[key] = value / sum_value
    prop_dict = {}
    prop_dict["cate"] = list(proportion_dict.keys())
    prop_dict["prop"] = list(proportion_dict.values())
    df_prop = pd.DataFrame(prop_dict)
    # df_prop.sort_values(by="prop",inplace=True)
    prop_path = PROJECT_FILE + f"/{projectName}/cdr3_share/prop_pep"  #"prop_pep"  每一种情况的cdr3的占比,shape[0]
    dir = os.path.split(file_path)
    save_path = prop_path + f"/{group}"
    mkidrs(save_path)
    df_prop.to_csv(os.path.join(save_path, dir[1]), index=False)

def mkidrs(path: str) -> None:
    """
    检查并创建目录。
    """
    try:
        if not os.path.exists(path):
            os.makedirs(path)
    except Exception as  e:
        pass

# from concurrent.futures import *
# from multiprocessing import cpu_count

# core_num = cpu_count()
# if __name__ == '__main__':
#     with ProcessPoolExecutor(max_workers=core_num) as executor:
#             results = executor.map(arrage,Csv_path)
import parmap


def start_func(projectName: str) -> None:
    """
    启动并行化的肽段统计整理流程。
    """
    # datas:[file_path,projectName]
    Csv_path = get_Csv_path(projectName)
    datas = []
    for path in Csv_path:
        datas.append([path, projectName])
    # for data in datas:
    #     # print(data)
    #     arrage(data)
    runtime = parmap.map_async(arrage, datas)
    runtime.wait()
    result = runtime.get()

#
# for file_path in Csv_path:
#     arrage(file_path)
