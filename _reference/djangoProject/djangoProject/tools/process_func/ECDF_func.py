import shutil

from appone.constant import PROJECT_FILE,DBURL,PROJECT_DB_NAME,PROJECT_COLLECTION_NAME,PROJECT_DATAPOINT_COLLECTION_NAME
import  os
import pandas as  pd
import pymongo
from djangoProject.tools.process_func import utils
from djangoProject.tools.process_script.ECDF import ECDF
from djangoProject.tools.logger import log
logger = log.GetLogger().get_logger()

from typing import List


def get_use_df(datapoint: pd.DataFrame, df: pd.DataFrame, category: List[str]) -> pd.DataFrame:
    """
    根据数据点、原始 DataFrame 和分类列表，生成用于 ECDF 计算的 DataFrame。
    """
    datapoint = datapoint[["sample"] + category]
    datapoint.rename(columns={"sample": "CDR3(pep)"}, inplace=True)
    df_transposed = df.T
    df_transposed.reset_index(inplace=True)
    df_transposed.columns = df_transposed.iloc[0]
    df_transposed = df_transposed.iloc[1:, :]
    df_transposed["CDR3(pep)"] = df_transposed["CDR3(pep)"].map(lambda x: x.split("__")[0])
    df2 = pd.merge(datapoint, df_transposed, how="inner", on="CDR3(pep)")
    df23 = df2.T
    df23.reset_index(inplace=True)
    df23 = df23.T
    df23.columns = df23.iloc[0]
    df23.reset_index(inplace=True)
    df23 = df23.drop(columns=['index'])
    df23 = df23.iloc[1:, :].copy()
    df23 = df23.T
    df23.columns = df23.iloc[0]
    df23 = df23.iloc[1:, :]
    df23.reset_index(inplace=True)
    df23.rename(columns={"index": "CDR3(pep)"}, inplace=True)
    df23.to_csv("./ddd24.csv",index=False)
    df23222 = pd.read_csv("./ddd24.csv",low_memory=False)
    # 删除 csv文件
    os.remove("./ddd24.csv")
    return df23222


def ECDF_func(projectName: str) -> None:
    """
    执行指定项目的经验累积分布函数 (ECDF) 分析。
    """
    file = PROJECT_FILE+fr"/{projectName}/gene_usage/Pep_shared"
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        for dirname, dirs, filenames in os.walk(file):
            for filename in filenames:
                path = os.path.join(dirname, filename)
                df = pd.read_csv(path)
                project_db = client[PROJECT_DB_NAME]
                projectName_db = client[projectName]
                project_collection = project_db[PROJECT_COLLECTION_NAME]
                groupSpecification_collection = projectName_db['groupSpecification']
                sample_collection = projectName_db[PROJECT_DATAPOINT_COLLECTION_NAME]
                pro_id = project_collection.find({'name': projectName})[0]["id"]
                document = sample_collection.find({'project_id': pro_id})
                documents_list = list(document)
                datapoint = pd.DataFrame(documents_list)
                # category, index = utils.get_group_list(datapoint)
                arrange_dict = groupSpecification_collection.find({'name': projectName})[0]["groupSpecification"]

                for group in arrange_dict:
                    group_list = [group]
                    use_df = get_use_df(datapoint, df, group_list)
                    ECDF.start_func(use_df, projectName,arrange_dict[group],filename[:-4],group)
    except Exception as e:
        # print(e)
        logger.error(f"{projectName}ECDF_func func出现错误:{e}")
    finally:
        client.close()
        # if os.path.exists(file):
        #     shutil.rmtree(file)
        #     print("删除Pep_shared文件夹")
        # else:
        #     print("Pep_shared文件夹不存在")


if __name__ == '__main__':
    ECDF_func("AAAAAtest")