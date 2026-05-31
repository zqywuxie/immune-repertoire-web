import shutil

import pandas as pd
import os
import parmap
import pymongo
from appone.constant import DBURL, PROJECT_DB_NAME, PROJECT_COLLECTION_NAME, PROJECT_DATAPOINT_COLLECTION_NAME, \
    PROJECT_FILE
from djangoProject.tools.process_func import utils
import warnings
from typing import List, Dict, Tuple, Any
from djangoProject.tools.logger import log

logger = log.GetLogger().get_logger()
warnings.filterwarnings("ignore", category=FutureWarning)


# def get_chain2file():
#     chain2file = {}
#     for dirname, dirs, filenames in os.walk("./pep_data"):
#         for filename in filenames:
#             chain = dirname.split("/")[-1]
#             if chain not in chain2file.keys():
#                 chain2file[chain] = [os.path.join(dirname, filename)]
#             else:
#                 chain2file[chain].append(os.path.join(dirname, filename))


def read_csv(path: List[Any]) -> pd.DataFrame:
    """
    读取并处理单个样本的 CDR3 数据，计算其长度分布。
    """
    df = path[0]
    df = df[["CDR3(pep)", "copy"]]
    # db = pd.read_csv(path, usecols=["CDR3(pep)", "copy"])
    if df.shape[0] == 0:
        return pd.DataFrame(columns=["CDR3(pep)", "copy", "CDR3_Lenth"])
    df = df.groupby("CDR3(pep)").sum().reset_index().sort_values(by="copy", ascending=False)
    df["CDR3_Lenth"] = df["CDR3(pep)"].str.len()
    # CDR3_lenth_file = "CDR3_lenth_distribution/" + path.split("__")[-1].split(".csv")[0]
    # db.to_csv(CDR3_lenth_file + "/" + path.split("/")[-1], index=False)
    df_lenth_distribution = df[["copy", "CDR3_Lenth"]].groupby(by="CDR3_Lenth").sum()
    df_lenth_distribution = df_lenth_distribution / df_lenth_distribution.sum()
    df_lenth_distribution.columns = [path[1]]  #[path.split("/")[-1]]  # sample_name
    df_lenth_distribution = df_lenth_distribution.reset_index()
    return df_lenth_distribution


def get_chain2df(chain2file: Dict[str, List[List[Any]]]) -> Dict[str, List[pd.DataFrame]]:
    """
    并行处理不同链的样本数据，获取对应的长度分布 DataFrame 列表。
    """
    chain2df = {}
    for chain, dfs in chain2file.items():
        # CDR3_lenth_file = "CDR3_lenth_distribution/"+chain
        # if not os.path.exists(CDR3_lenth_file):
        #     os.makedirs(CDR3_lenth_file)
        result = parmap.map_async(read_csv, dfs)
        result.wait()
        output = result.get()
        chain2df[chain] = output
    return chain2df


def save_df(chain2df: Dict[str, List[pd.DataFrame]], category: List[str], datapoint: pd.DataFrame, projectName: str) -> Tuple[pd.DataFrame, List[List[Any]]]:
    """
    保存各个链的 CDR3 长度矩阵和平均长度数据。
    """
    # category = "HHY"
    # file_name = "./Profile_All_24_04_22.csv"

    df_all = pd.DataFrame(columns=["sample"])
    CDR3_distribution_matrix_chain_list = []
    for chain, dfs_lenth_distribution in chain2df.items():
        df = pd.DataFrame(columns=["CDR3_Lenth"])
        for df_lenth_distribution in dfs_lenth_distribution:
            # print(df_lenth_distribution)
            df = pd.merge(df, df_lenth_distribution, on="CDR3_Lenth", how="outer")
            df = df.sort_values(by="CDR3_Lenth", ascending=True)
            df = df.fillna(0)
        df_len_matrix = df.copy()
        df_len_matrix.index = df_len_matrix.pop("CDR3_Lenth")
        df_len_matrix = df_len_matrix.T.reset_index()
        df_len_matrix["index"] = df_len_matrix["index"]  #.apply(lambda x:x.split("__")[0])
        df_len_matrix.insert(loc=0, column="sample", value=df_len_matrix.pop("index"))
        # print("df_len_matrix", df_len_matrix)
        # df_dp = pd.read_csv(file_name,usecols=["Sample",category])
        df_dp = datapoint[["sample"] + category]
        # df_dp = df_dp.dropna()
        df_len_matrix = pd.merge(df_dp, df_len_matrix, how="inner", on="sample")
        save_path = PROJECT_FILE + F"/{projectName}/cdr3_length/"
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        df_len_matrix.to_csv(save_path+"CDR3_distribution_matrix_"+chain+".csv",index=False)
        # df_len_matrix.to_csv("CDR3_distribution_matrix_"+chain+".csv",index=False)
        CDR3_distribution_matrix_chain_list.append([df_len_matrix, chain])
        mean_lenth_df = pd.DataFrame(
            df[df.columns[1:]].apply(lambda x: x * df["CDR3_Lenth"], axis=0).sum()).reset_index()
        mean_lenth_df.columns = ["sample", chain + "_meanCDR3_len"]
        mean_lenth_df["sample"] = mean_lenth_df["sample"].apply(lambda x: x.split("__")[0])
        df_all = pd.merge(df_all, mean_lenth_df, how="outer", on="sample")
    df_dp = datapoint[["sample"] + category]
    # df_dp = df_dp.dropna()
    df_all = pd.merge(df_dp, df_all, how="inner", on="sample")
    save_path = PROJECT_FILE + F"/{projectName}/cdr3_length/"
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    df_all.to_csv(save_path+"CDR3_lenth.csv",index=False)
    CDR3_lenth_df = df_all
    return CDR3_lenth_df, CDR3_distribution_matrix_chain_list


def start_func(chain2file: Dict[str, List[List[Any]]], category: List[str], datapoint: pd.DataFrame, projectName: str) -> None:
    """
    启动 CDR3 长度分析流程：处理数据、保存结果、并生成箱线图。
    """
    chain2df = get_chain2df(chain2file)
    CDR3_lenth_df, CDR3_distribution_matrix_chain_list = save_df(chain2df, category, datapoint,projectName)
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        db = client[projectName]
        collection_name = db["CDR3_length"]
        data = {
            "projectName": projectName,
            "CDR3_lenth_df": CDR3_lenth_df.to_dict(orient="list"),
        }
        for chain_list in CDR3_distribution_matrix_chain_list:
            df = chain_list[0]
            df.columns = df.columns.astype(str)
            chain = chain_list[1]
            chain = str(chain)
            data[f"CDR3_distribution_matrix_{chain}"] = df.to_dict(orient="list")
        # print(data.keys())
        collection_name.insert_one(data)

        to_boxplot(CDR3_lenth_df, CDR3_distribution_matrix_chain_list, db, projectName)
    except Exception as e:
        # print(e)
        logger.error(f"{projectName}get_cdr3_length start_func出现错误:{e}")
    finally:
        client.close()
    # to boxplot


def to_boxplot(CDR3_lenth_df: pd.DataFrame, CDR3_distribution_matrix_chain_list: List[List[Any]], db: pymongo.database.Database, projectName: str) -> None:
    """
    为平均长度和长度分布矩阵生成箱线图。
    """
    from appone.constant import CDR3_LENGTH_DIRNAME
    dirname = CDR3_LENGTH_DIRNAME
    utils.get_boxplot_condition(CDR3_lenth_df, projectName, db, dirname)
    src_folder = PROJECT_FILE + f"/{projectName}/boxplot/{dirname}"
    target_path = PROJECT_FILE + f"/{projectName}/cdr3_length/length_boxplot/"
    shutil.copytree(src_folder, target_path)  # 复制
    shutil.rmtree(src_folder)
    for chain_list in CDR3_distribution_matrix_chain_list:
        df = chain_list[0]
        chain = chain_list[1]
        CDR3_distribution_matrix_dirname = f"CDR3_distribution_matrix_{chain}_boxplot"
        utils.get_boxplot_condition(df, projectName, db, CDR3_distribution_matrix_dirname)
        src_folder = PROJECT_FILE + f"/{projectName}/boxplot/CDR3_distribution_matrix_{chain}_boxplot/"
        target_path = PROJECT_FILE + f"/{projectName}/cdr3_length/CDR3_distribution_matrix_{chain}_boxplot"
        shutil.copytree(src_folder, target_path)  # 复制
        shutil.rmtree(src_folder)
