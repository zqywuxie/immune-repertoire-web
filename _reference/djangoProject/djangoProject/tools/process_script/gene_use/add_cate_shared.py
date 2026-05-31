import pandas as pd
import os
import numpy as np
from appone.constant import PROJECT_FILE
import warnings
from typing import List, Dict, Any

# 把pep_shared 的文件中拿出只属于这一组的列，添加分组信息
warnings.filterwarnings("ignore", category=FutureWarning)
# datapoint_path = "datapoint.csv"
# index_sorted = ["Baseline", "0-1h", "24h", "48h"]
# # Group = "group1"
# # dp_df = pd.read_csv(datapoint_path)

"在这里的会提前排序，没在这里面的会放到后面但是不会删除"
remove_list = [np.nan]


def get_Pep_paths(projectName: str) -> List[str]:
    """
    获取指定项目下所有肽段共享数据的文件路径。
    """
    Pep_paths = []
    path = PROJECT_FILE + f"/{projectName}/gene_usage/Pep_shared"
    for dirname, dirs, filenames in os.walk(path):
        for filename in filenames:
            Pep_paths.append(os.path.join(dirname, filename))
    return Pep_paths


def add_cate(data_list: List[Any]) -> None:
    """
    为肽段共享数据添加分类信息并保存。
    """
    file_path = data_list[0]
    dp_df = data_list[1]
    index_sorted = data_list[2]
    Group = data_list[3]
    projectName = data_list[4]
    pep_df = pd.read_csv(file_path)
    cate_dict = {'CDR3(pep)': ['category']}
    # pep_cate = ["category"]
    for pep_name in pep_df[pep_df.columns[1:]]:
        for name_dp in dp_df[dp_df.columns[0]]:
            pep_name_split = pep_name.split("__")
            samplename = ""
            for str_split in pep_name_split[:-1]:
                samplename = samplename + str_split + "__"
            samplename = samplename[:-2]
            if samplename == name_dp:
                # print(name_dp, pep_name.split("__")[0])
                cate_dict[pep_name] = [dp_df[dp_df[dp_df.columns[0]] == name_dp][Group].values.tolist()[0]]
                break
    # cate_dict = {}
    # for i in range(len(pep_cate)):
    #     if type(pep_cate[i]) != str:
    #         if np.isnan(pep_cate[i]):
    #             continue
    #     cate_dict[pep_df.columns[i]] = [pep_cate[i]]
    remove_key = []
    # print(remove_list)
    for item in cate_dict.items():
        for key in remove_list:
            if key is np.nan:
                if pd.isna(item[1][0]):
                    remove_key.append(item[0])
            else:
                if item[1][0] is key:
                    remove_key.append(item[0])
    # print("remove_key", remove_key)
    for key in remove_key:
        cate_dict.pop(key)

    cate_df = pd.DataFrame(cate_dict)
    pep_df = pd.concat([cate_df, pep_df[list(cate_dict.keys())]])
    categorys = sorted(list(pep_df.iloc[0].unique()[1:]))  #
    index_sorted.reverse()
    if len(index_sorted):
        for cate in index_sorted:
            if cate in categorys:
                categorys.remove(cate)
                categorys.insert(0, cate)
    categorys.reverse()
    categorys_dict = {}
    for col in pep_df.columns[1:]:
        if pep_df[col].iloc[0] == " ":
            break
        else:
            if pep_df[col].iloc[0] not in list(categorys_dict.keys()):
                categorys_dict[pep_df[col].iloc[0]] = [col]
            else:
                categorys_dict[pep_df[col].iloc[0]].append(col)
    for category in categorys:
        for col in categorys_dict[category]:
            col_t = pep_df[col]
            pep_df.drop(columns=col, inplace=True)
            pep_df.insert(1, col, col_t)
    "./Pep_shared_cate"
    save_path = PROJECT_FILE + f"/{projectName}/gene_usage/Pep_shared_cate/{Group}"
    filename = os.path.split(file_path)[1]
    # dir = os.path.split(file_path)
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    pep_df.to_csv(os.path.join(save_path, filename), index=False)


from concurrent.futures import *
from multiprocessing import cpu_count

core_num = cpu_count()


def start_func(projectName: str, groupSpecification: Dict[str, List[str]], datapoint_df: pd.DataFrame) -> None:
    """
    启动肽段分类信息添加流程。
    """
    # datas: [file_path,dp_df,index_sorted,Group,projectName]
    Pep_paths = get_Pep_paths(projectName)
    datas = []
    for Group in groupSpecification:
        for filepath in Pep_paths:
            datas.append([filepath, datapoint_df, groupSpecification[Group], Group, projectName])
    for data in datas:
        # print(data[3])
        add_cate(data)


# if __name__ == '__main__':
#     with ProcessPoolExecutor(max_workers=core_num) as executor:
#         results = executor.map(add_cate, Pep_paths)

# for filepath in Pep_paths:
#     add_cate(filepath)
