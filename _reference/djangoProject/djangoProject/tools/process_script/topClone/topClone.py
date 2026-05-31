import shutil

import pandas as pd
import os

from djangoProject.tools.process_func.utils import get_boxplot_condition
from djangoProject.tools.process_script.boxplot import BoxPlot_1120_Thread_Arrange
from appone.constant import DBURL, PROJECT_DB_NAME, PROJECT_COLLECTION_NAME, PROJECT_DATAPOINT_COLLECTION_NAME, \
    PROJECT_FILE
import pymongo
from djangoProject.tools.process_func import utils
import warnings
from typing import Dict, List, Any

warnings.filterwarnings("ignore", category=FutureWarning)


def get_topclone_df(param_dict: Dict[str, Dict[str, pd.DataFrame]], datapoint: pd.DataFrame, projectName: str) -> Dict[str, pd.DataFrame]:
    """
    计算各样本各链的 Top Clone 比例，并返回结果 DataFrame 字典。
    """
    return_dict = {}
    for chain in param_dict:
        topclone_dict = {"top10" + chain: {}, "top20" + chain: {}, "top50" + chain: {}, "top100" + chain: {}}
        topCDR3_dict = {"top10" + chain: {}, "top20" + chain: {}, "top50" + chain: {}, "top100" + chain: {}}
        for sample in param_dict[chain]:
            df_pep = param_dict[chain][sample]
            df_pep = df_pep[["CDR3(pep)", "copy"]]
            df_pep_CDR3copy = df_pep.groupby(by="CDR3(pep)").sum().reset_index()
            df_copy = df_pep_CDR3copy[~df_pep_CDR3copy["CDR3(pep)"].str.contains("\*|_")].sort_values("copy",
                                                                                                      ascending=False)
            topCDR3_dict["top10" + chain][sample] = df_copy["CDR3(pep)"].iloc[:10].tolist()
            topCDR3_dict["top20" + chain][sample] = df_copy["CDR3(pep)"].iloc[:20].tolist()
            topCDR3_dict["top50" + chain][sample] = df_copy["CDR3(pep)"].iloc[:50].tolist()
            topCDR3_dict["top100" + chain][sample] = df_copy["CDR3(pep)"].iloc[:100].tolist()
            top10_proportion = df_copy["copy"].iloc[:10].sum() / df_copy["copy"].sum()
            top20_proportion = df_copy["copy"].iloc[:20].sum() / df_copy["copy"].sum()
            top50_proportion = df_copy["copy"].iloc[:50].sum() / df_copy["copy"].sum()
            top100_proportion = df_copy["copy"].iloc[:100].sum() / df_copy["copy"].sum()
            topclone_dict["top10" + chain][sample] = top10_proportion
            topclone_dict["top20" + chain][sample] = top20_proportion
            topclone_dict["top50" + chain][sample] = top50_proportion
            topclone_dict["top100" + chain][sample] = top100_proportion

        topclone_df = pd.DataFrame(topclone_dict)
        topclone_df.index.name = "sample"
        topclone_df = topclone_df.reset_index()
        df = datapoint
        df = pd.merge(df, topclone_df, on="sample")
        data = {
            "projectName": projectName,
            "chain": chain,
            "topClone_df": df.to_dict(orient="list")
        }
        utils.data_save_to_db(data, "topClone", projectName)
        # db.to_csv(f"./topclone_{chain}.csv", index=False)
        from appone.constant import PROJECT_FILE
        save_path = PROJECT_FILE + "/" + projectName + "/cdr3_clone/topClone/"
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        # print(df)
        df.to_csv(save_path + chain + ".csv", index=False)
        return_dict[chain] = df
    return return_dict


def to_boxplot(df: pd.DataFrame, projectName: str, chain: str, is_p_value_flag2: bool = True) -> None:
    """
    为 Top Clone 结果生成箱线图。
    """
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        db = client[projectName]
        # topClone_collection = db['topClone']
        # data = {
        #     "projectName": projectName,
        #     "topClone_df": db.to_dict(orient="records")
        # }
        # topClone_collection.insert_one(data)
        get_boxplot_condition(df, projectName, db, f"topClone_{chain}")
        # df, projectName, db, boxplot_dirname,
        # arrange_dict = groupSpecification_collection.find({'name': projectName})[0]["groupSpecification"]
        # data_split_point_begin2 = "group1"
        # index = 2
        # data_split_point_over2 = "group" + str(index)
        # while data_split_point_over2 in df.columns:
        #     index = index + 1
        #     data_split_point_over2 = "group" + str(index)
        # data_split_point_over2 = "group" + str(index - 1)
        # from appone.constant import TOPCLONE_DIRNAME
        # BoxPlot_1120_Thread_Arrange.start_func(df, arrange_dict, projectName, data_split_point_begin2,
        #                                        data_split_point_over2,
        #                                        is_p_value_flag2, TOPCLONE_DIRNAME, param_begin2=df.columns.tolist()[index-1],
        #                                        param_over2=df.columns.tolist()[-1])
    except Exception as e:
        print("出现错误:", e)
    finally:
        client.close()


# {
#         "TRA":{
#             "E0_1_B":pd.DataFrame,
#             "E0_2_B":pd.DataFrame
#         },
#         "TRB":{
#             "E0_1_B":pd.DataFrame,
#             "E0_2_B":pd.DataFrame
#         }
#     }

#db = pd.read_csv("./Profile_All_24_04_22.csv",usecols=["sample"]+categorys)
def start_func(param_dict: Dict[str, Dict[str, pd.DataFrame]], datapoint: pd.DataFrame, projectName: str) -> None:
    """
    启动 Top Clone 分析流程。
    """
    return_dict = get_topclone_df(param_dict, datapoint, projectName)
    for k,v in return_dict.items():
        chain = k
        df = v
        to_boxplot(df, projectName,chain)
        src_folder = PROJECT_FILE + f"/{projectName}/boxplot/topClone_{chain}"
        target_path = PROJECT_FILE + f"/{projectName}/cdr3_clone/topClone/boxplot_{chain}"
        shutil.copytree(src_folder, target_path)  # 复制
        shutil.rmtree(src_folder)
