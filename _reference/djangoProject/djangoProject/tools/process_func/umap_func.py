from djangoProject.tools.process_script.umap import Umap_12_08
from appone.constant import DBURL, PROJECT_DATAPOINT_COLLECTION_NAME, PROJECT_DB_NAME, PROJECT_COLLECTION_NAME
import pandas as pd

import pymongo
from djangoProject.tools.logger import log
logger = log.GetLogger().get_logger()


def umap_func(projectName: str) -> None:
    """
    为指定项目执行 UMAP 降维分析。
    """
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        db = client[projectName]
        sample_collection = db[PROJECT_DATAPOINT_COLLECTION_NAME]
        project_collection = client[PROJECT_DB_NAME][PROJECT_COLLECTION_NAME]
        pro_id = project_collection.find({'name': projectName})[0]["id"]
        # pro_id = pro_col.find({'name': projectName})[0]["id"]
        boxplot_coll_name = db[projectName + "_boxplot_pvalue"]
        gene_use_coll = db[projectName + '_gene_usage']
        group_list = []
        group_l = list(boxplot_coll_name.find({}, {"group": 1, "_id": 0}))
        for l in group_l:
            group_list.append(l["group"])
        for group in set(group_list):
            df_all = get_df_all(group, boxplot_coll_name, sample_collection, pro_id, gene_use_coll)
            if len(df_all.columns.tolist()) >= 3:
                param_begin = df_all.columns.tolist()[2]
                param_over = df_all.columns.tolist()[-1]
                # print(df_all)
                Umap_12_08.start_func(df_all, projectName, group, param_begin, param_over)
            else:
                logger.info(f"{projectName}的该组{group}数据不足3个{df_all.columns.tolist()},有问题,无法进行umap")
                print(f"{projectName} 该组{group}数据不足3个{df_all.columns.tolist()},有问题,无法进行umap")
    except Exception as e:
        # print(f"{projectName},{projectName},{e}")
        logger.error(f"{projectName},{group},{e}")
    finally:
        client.close()

def get_df_all(group: str, boxplot_coll_name: pymongo.collection.Collection, sample_collection: pymongo.collection.Collection, pro_id: str, gene_use_coll: pymongo.collection.Collection) -> pd.DataFrame:
    """
    合并箱线图 P 值数据和基因使用 P 值数据。
    """
    df = get_p_value_df(group, boxplot_coll_name, sample_collection, pro_id)
    df_gene = get_gene_have_pvalue_df(group, gene_use_coll)
    df_all = pd.merge(df, df_gene, how="inner", on="sample")
    return df_all


def get_p_value_df(group: str, boxplot_coll_name: pymongo.collection.Collection, sample_collection: pymongo.collection.Collection, pro_id: str) -> pd.DataFrame:
    """
    从箱线图结果中提取显著（P < 0.05）的特征列并返回 DataFrame。
    """
    # 获取所有的p_value colums
    s_list = list(boxplot_coll_name.find({
        "$and": [
            {"group": group},
            {"category": "profile_boxplot"}
        ]
    }, {"p_value": 1, "_id": 0}))
    have_p_value_column = []
    s_df = pd.DataFrame(s_list[0]["p_value"])
    s_df = s_df.iloc[:, 1:]
    for i in s_df.columns:
        row = s_df[i]
        for element in row:
            if element < 0.05:
                have_p_value_column.append(i)
    have_p_value_column = list(set(have_p_value_column))
    document = sample_collection.find({"project_id": pro_id}, {"_id": 0})
    documents_list = list(document)
    have_p_value_column.insert(0, group)
    have_p_value_column.insert(0, "sample")
    df = pd.DataFrame(documents_list)
    df = df[have_p_value_column]
    # df.dropna(axis=0, inplace=True)
    return df


def get_gene_have_pvalue_df(group: str, gene_use_coll: pymongo.collection.Collection) -> pd.DataFrame:
    """
    从基因使用结果中提取显著的特征列并返回 DataFrame。
    """
    from appone.constant import CHAIN_TYPES
    v_or_j_groups = ["1Vusage", "1Jusage", "1VJusage"]
    v_or_j_group_df_list = []
    for v_or_j_group in v_or_j_groups:
        chain_df_list = []
        for chain_type in CHAIN_TYPES:
            gene = list(gene_use_coll.find({"group": group, "v_or_j_usage": v_or_j_group, "type": chain_type},
                                           {"_id": 0, "pvalue_df": 1, "df_use": 1}))
            if len(gene) == 0:
                continue
            dict_list = []
            for g in gene:
                aa = g["df_use"]
                dict_list.append(aa)
            for d in dict_list:
                df = pd.DataFrame(d)
                df.drop("Category", axis=1, inplace=True)
                df["sample"] = df["sample"].apply(lambda x: x.split("__")[0])
                chain_df_list.append(df)
        if len(chain_df_list) == 0:
            continue
        if len(chain_df_list) == 1:
            df_chain = chain_df_list[0]
        else:
            df_chain = chain_df_list[0]
            for df in chain_df_list[1:]:
                df_chain = pd.merge(df_chain, df, how="inner", on="sample")
        v_or_j_group_df_list.append(df_chain)
    if len(v_or_j_group_df_list) == 0:
        return pd.DataFrame()
    df_v_or_j_group = v_or_j_group_df_list[0]
    if len(v_or_j_group_df_list) > 1:
        for df in v_or_j_group_df_list[1:]:
            df_v_or_j_group = pd.merge(df_v_or_j_group, df, how="inner", on="sample")
    # df_v_or_j_group.drop(["Category"], axis=1, inplace=True)
    return df_v_or_j_group

    #     gene = list(gene_use_coll.find({"group": group, "v_or_j_usage": {"$in": [v_or_j_group]}},
    #                                    {"_id": 0, "pvalue_df": 1}))
    #     gene_have_p_value_column = []
    #     for g in gene:
    #         df = pd.DataFrame(g["pvalue_df"])
    #         df = df.iloc[:, 1:]
    #         for i in df.columns:
    #             row = df[i]
    #             for element in row:
    #                 if element < 0.05:
    #                     gene_have_p_value_column.append(i)
    #
    #     gene_have_p_value_column = list(set(gene_have_p_value_column))
    #
    #     df_use_list = list(
    #         gene_use_coll.find({"group": group, "v_or_j_usage": {"$in": [v_or_j_group]}}, {"_id": 0, "df_use": 1}))
    #     df_use_all = pd.DataFrame(columns=["sample", "Category"])
    #     for df_use in df_use_list:
    #         df_use1 = pd.DataFrame(df_use["df_use"])
    #         df_use_all = pd.merge(df_use_all, df_use1, how="inner",  on="sample")
    #     gene_have_p_value_column.insert(0, "Category")
    #     gene_have_p_value_column.insert(0, "sample")
    #     df_use_all = df_use_all[gene_have_p_value_column]
    #     df_use_all.rename(columns={"Category": group}, inplace=True)
    #     for index, row in df_use_all.iterrows():
    #         df_use_all.loc[index, "sample"] = row["sample"].split("__")[0]
    # return df_use_all


if __name__ == '__main__':
    umap_func("6_4")
