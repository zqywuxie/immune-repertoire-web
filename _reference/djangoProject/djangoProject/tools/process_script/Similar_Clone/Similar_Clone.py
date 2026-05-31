import pandas as pd
import os
from itertools import combinations, product
from fuzzywuzzy import fuzz
from multiprocessing import Pool, Manager
import numpy as np
import seaborn as sns
from typing import List, Dict, Tuple, Any

import warnings

warnings.filterwarnings("ignore")

cpu_count = os.cpu_count() or 1
threshold = 90


def calculate_fuzzy_cdr3(lenth: int, VJpair: str, dfs: List[pd.DataFrame], P_list: List[Any], cate_path: str) -> None:
    """
    计算给定长度和 VJ 对下，不同样本间 CDR3 序列的模糊匹配相似性。
    """
    CDR3_list = []
    for df in dfs:
        CDR3_list = list(set(CDR3_list) | set(df["CDR3(pep)"].values))
    forward_Edges = {}
    reverse_Edges = {}
    if len(CDR3_list) < 2:
        return None
    for CDR3_1 in CDR3_list:
        j = CDR3_list.index(CDR3_1) + 1
        for CDR3_2 in CDR3_list[j:]:
            if fuzz.ratio(CDR3_1, CDR3_2) > threshold:
                forward_Edges[CDR3_1] = CDR3_2
                reverse_Edges[CDR3_2] = CDR3_1
    shared_CDR3s = list(set(forward_Edges.keys()) | set(reverse_Edges.keys()))
    # 每个分组下 每个vj,cdr3_length组合相似的所有cdr3集合
    pd.DataFrame({"CDR3s": shared_CDR3s}).to_csv(cate_path + "/" + VJpair.replace(";", "_") + "_" + str(lenth) + ".csv",
                                                 index=False)
    P_list.append(((lenth, VJpair), shared_CDR3s))


def calculate_result(projectName: str, pep_files_dict: Dict[str, Dict[str, Any]], group: str, categorys_all: List[str], reference_df: pd.DataFrame) -> None:
    """
    计算并保存指定项目和分组下的克隆相似性分析结果。
    """
    category_col = group
    for chain in pep_files_dict.keys():
        from appone.constant import PROJECT_FILE
        path = PROJECT_FILE + "/" + projectName+"/Similar_Clone" + "/" + group + "/Edges/"
        chain_path = path + chain + "/"
        VJ_len_prolong_CDR3_num_dict = {}
        VJ_len_all_CDR3_num_dict = {}
        VJ_CDR3_num_dict = {}
        save_df_dict = {"sample": [], "category": [], "vj_len_proportion": [], "all_CDR3_proportion": []}
        save_df_vj_dict = {}
        all_cdr3_dict = {}

        for category in categorys_all:
            cate_path = os.path.join(chain_path, category)
            if not os.path.exists(cate_path):
                os.makedirs(cate_path)
            sample_names = reference_df[reference_df[category_col].astype(str) == category]["sample"].values.tolist()
            use_df_list = []
            for sample_name in sample_names:
                try:
                    path_df = pep_files_dict[chain][sample_name]
                    fields = {"CDR3(pep)": 1, 'V': 1, 'J': 1, 'copy': 1}
                    results = list(path_df.find({}, fields))
                    df = pd.DataFrame(results)
                    df_pep = df.groupby(
                        ["CDR3(pep)", "V", "J"]).sum().reset_index()
                    # print(df_pep.shape)
                    use_df_list.append(df_pep)
                except:
                    continue
            # use_df_list = [pd.read_csv(pep_files_dict[chain][sample_name],usecols=["CDR3(pep)","V","J","copy"]).groupby(["CDR3(pep)","V","J"]).sum().reset_index() for sample_name in sample_names]
            use_df_list = [use_df[~use_df["CDR3(pep)"].str.contains("[\*_]")] for use_df in use_df_list]
            for use_df in use_df_list:
                use_df["CDR3_lenth"] = use_df["CDR3(pep)"].str.len()
                use_df["VJ"] = use_df["V"] + [";"] * len(use_df["V"]) + use_df["J"]
                # use_df_list_V = [use_df[use_df["V"].isin(use_ful_V)] for use_df in use_df_list]
            use_df_list_V = use_df_list
            vj_list = use_df_list_V[0].VJ.unique().tolist()
            CDR3_lenth_list = use_df_list_V[0].CDR3_lenth.unique().tolist()
            for use_df in use_df_list_V[1:]:
                vj_list = list(set(vj_list).union(set(use_df.VJ.unique().tolist())))
                CDR3_lenth_list = list(set(CDR3_lenth_list).intersection(set(use_df.CDR3_lenth.unique().tolist())))

            VJ_CDR3_same_dict = {}
            for VJ in vj_list:
                for CDR3_LENTH in CDR3_lenth_list:
                    pre_df_list = [use_df[(use_df.CDR3_lenth == CDR3_LENTH) & (use_df.VJ == VJ)] for use_df in
                                   use_df_list_V]
                    shape_list = [use_df.shape[0] for use_df in pre_df_list]
                    # if 0 in shape_list:
                    #     continue
                    VJ_CDR3_same_dict[(CDR3_LENTH, VJ)] = pre_df_list

            Process_pool = Pool(min(cpu_count, 128))
            P_list = Manager().list()
            for ((lenth, VJpair), dfs) in VJ_CDR3_same_dict.items():
                Process_pool.apply_async(calculate_fuzzy_cdr3, (lenth, VJpair, dfs, P_list, cate_path))
            Process_pool.close()
            Process_pool.join()
            P_list = list(P_list)
            # for item in P_list:
            use_vj_dict = {}
            P_list = [x for x in P_list if x is not None]
            for sample_name in sample_names:
                use_vj_dict[sample_name] = {}

            # CDR3s    (lenth,VJpair) ->item 分组下所有类似cdr3
            for (item, CDR3s) in P_list:
                vj = item[1]
                for sample_name, sample_df, use_df in zip(sample_names, VJ_CDR3_same_dict[item], use_df_list_V):
                    if vj not in use_vj_dict[sample_name].keys():
                        use_vj_dict[sample_name][vj] = []
                    use_vj_dict[sample_name][vj] += sample_df["CDR3(pep)"].values.tolist()
                    contain_CDR3 = list(set(CDR3s) & set(sample_df["CDR3(pep)"].values))
                    prolong_CDR3_num = sample_df[sample_df["CDR3(pep)"].isin(contain_CDR3)]["copy"].sum()
                    VJ_all_CDR3_num = sample_df["copy"].sum()
                    if sample_name not in VJ_len_prolong_CDR3_num_dict.keys():
                        VJ_len_prolong_CDR3_num_dict[sample_name] = prolong_CDR3_num
                        VJ_len_all_CDR3_num_dict[sample_name] = VJ_all_CDR3_num
                    else:
                        VJ_len_prolong_CDR3_num_dict[sample_name] += prolong_CDR3_num
                        VJ_len_all_CDR3_num_dict[sample_name] += VJ_all_CDR3_num

            for ((sample_name, VJ_CDR3s_dict), ref_df) in zip(use_vj_dict.items(),
                                                              use_df_list_V):  # use_vj_dict  (sample,vj)所有的cdr3
                VJ_CDR3_num_dict[sample_name] = {"sample": [sample_name]}
                for (vj, CDR3s) in VJ_CDR3s_dict.items():
                    vj_clone_all_num = ref_df[ref_df["VJ"] == vj]["copy"].sum()
                    if vj_clone_all_num == 0:
                        continue
                    vj_use_df = ref_df[ref_df["VJ"] == vj]
                    vj_clone_use_num = vj_use_df[vj_use_df["CDR3(pep)"].isin(CDR3s)]["copy"].sum()
                    VJ_CDR3_num_dict[sample_name][vj] = [vj_clone_use_num / vj_clone_all_num]

            for sample_name, use_df in zip(sample_names, use_df_list_V):
                all_cdr3_dict[sample_name] = use_df["copy"].sum()

        for key, values in VJ_len_prolong_CDR3_num_dict.items():
            # 每一个sample 具有相似性的所有的cdr3的copy的累加和 / 在每一个个vj,length组合下的cdr3的copy的累加和
            save_df_dict["vj_len_proportion"].append(VJ_len_prolong_CDR3_num_dict[key] / VJ_len_all_CDR3_num_dict[key])
            # 每一个sample 具有相似性的所有的cdr3的copy的累加和 / 这个原来的df的copy和
            save_df_dict["all_CDR3_proportion"].append(VJ_len_prolong_CDR3_num_dict[key] / all_cdr3_dict[key])
            save_df_dict["sample"].append(key)
            save_df_dict["category"].append(reference_df[reference_df["sample"] == key][category_col].values[0])

        vj_split_df = pd.DataFrame()
        first_flag = True
        category_list = []
        for (sample, df_dict) in VJ_CDR3_num_dict.items():
            if first_flag:
                first_flag = False
                vj_split_df = pd.DataFrame(df_dict)
            df_vj = pd.DataFrame(df_dict)
            vj_split_df = pd.merge(df_vj, vj_split_df, how="outer")
            category_list.append(reference_df[reference_df["sample"] == sample][category_col].values[0])
        vj_split_df.insert(column="category", value=category_list, loc=1)
        #  vj_split_df
        vj_split_df.to_csv(chain_path + chain + "_vj_all.csv", index=False) # 每一个vj组合的相似cdr3/这一个vj组合的所有cdr3 考虑了copy
        pd.DataFrame(save_df_dict).to_csv(chain_path + "proportion_" + chain + ".csv", index=False)


def start_func(projectName: str, pep_files_dict: Dict[str, Dict[str, Any]], group_list: List[str], datapoint_df: pd.DataFrame) -> None:
    """
    启动相似克隆分析流程。
    """
    # pep_files_dict = {}
    # for dirname, dirs, filenames in os.walk("./pep_data/"):
    #     for chain in dirs:
    #         pep_files_dict[chain] = {}
    #     for filename in filenames:
    #         chain = filename.split("__")[-1].split(".csv")[0]
    #         pep_sample_name = filename.split("/")[-1].split("__")[0]
    #         pep_files_dict[chain][pep_sample_name] = os.path.join(dirname, filename)
    # todo parmap
    reference_df = datapoint_df
    for group in group_list:
        # NO_USE_CATEGORY = []
        NO_USE_CATEGORY = ["nan"]
        categorys_all = reference_df[group].unique().astype(str).tolist()
        # categorys_all.remove("nan")
        for category in NO_USE_CATEGORY:
            if category in categorys_all:
                categorys_all.remove(category)
        calculate_result(projectName, pep_files_dict, group, categorys_all, reference_df)
