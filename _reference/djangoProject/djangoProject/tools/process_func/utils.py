import pandas as pd
from djangoProject.tools.process_script.boxplot.BoxPlot_1120_Thread_Arrange import start_func
import pymongo
from appone.constant import DBURL, PROJECT_DATAPOINT_COLLECTION_NAME
from typing import Tuple, List, Any


def get_group_list(projectName: str) -> Tuple[List[str], int]:
    """
    获取指定项目的分组列表和分组数量。
    """
    projectName = str(projectName)
    client = pymongo.MongoClient(DBURL, maxidletimems=1200)
    db = client[projectName]
    groupSpecification_collection = db["groupSpecification"]
    arrange_dict = groupSpecification_collection.find({'name': projectName})[0]["groupSpecification"]
    Category = list(arrange_dict.keys())
    index = len(Category)
    return Category, index


def get_boxplot_condition(df: pd.DataFrame, projectName: str, db: pymongo.database.Database, boxplot_dirname: str) -> None:
    """
    根据给定的数据框和项目信息，执行箱线图绘制。
    """
    groupSpecification_collection = db['groupSpecification']
    arrange_dict = groupSpecification_collection.find({'name': projectName})[0]["groupSpecification"]
    Category, index = get_group_list(projectName)
    data_split_point_begin2 = Category[0]
    is_p_value_flag2 = True
    data_split_point_over2 = Category[-1]
    start_func(df, arrange_dict, projectName, data_split_point_begin2,
               data_split_point_over2,
               is_p_value_flag2, boxplot_dirname,
               param_begin2=df.columns.tolist()[index + 1],
               param_over2=df.columns.tolist()[-1])


def get_datapoint_df(projectName: str, db: pymongo.database.Database) -> pd.DataFrame:
    """
    从数据库中获取项目的数据点信息并转换为 DataFrame。
    """
    # project_collection = db['project']
    sample_collection = db[PROJECT_DATAPOINT_COLLECTION_NAME]
    # pro_id = project_collection.find({'name': projectName})[0]["id"]
    document = sample_collection.find()
    documents_list = list(document)
    datapoint = pd.DataFrame(documents_list)
    return datapoint


def data_save_to_db(data: Any, collection_name: str, projectName: str, is_many: bool = False) -> None:
    """
    将数据保存到指定的 MongoDB 集合中。
    """
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        db = client[projectName]
        collection = db[collection_name]
        if is_many:
            # print("many")
            collection_name.insert_many(data)
        else:
            # print("one")
            collection.insert_one(data)
    except Exception as e:
        print(e)
    finally:
        client.close()


def remove_sample_col(df: pd.DataFrame) -> pd.DataFrame:
    """
    从 DataFrame 中移除包含 'sample' 的列（从 'TRA_percent_reads_all' 列开始）。
    """
    index = df.columns.tolist().index('TRA_percent_reads_all')
    for col in df.columns.tolist()[index:]:
        if "sample" in col:
            df.drop(col, axis=1, inplace=True)
    return df
