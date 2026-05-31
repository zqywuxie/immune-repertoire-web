import pymongo
import pandas as pd
from appone.constant import DBURL,DB_DB_NAME,PROJECT_DB_NAME,PROJECT_DATAPOINT_COLLECTION_NAME,PROJECT_COLLECTION_NAME
from djangoProject.tools.process_script.Alignment import Alignment
from djangoProject.tools.process_func import utils
from djangoProject.tools.logger import log
logger = log.GetLogger().get_logger()

def insert_db() -> None:
    """
    如果数据库为空，则将 VDJ 和 McPAS-TCR 基础数据插入到 MongoDB 中。
    """
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        db = client[DB_DB_NAME]
        VDJ_DB2 = db["VDJ_DB2"]
        McPASTCR_DB = db["McPASTCR_DB"]
        # VDJ_DB2 为空 插入
        if not VDJ_DB2.find_one():
            df = pd.read_csv("./db/vdjdb.csv",low_memory=False)
            VDJ_DB2.insert_many(df.to_dict(orient="records"))
        # McPASTCR_DB 为空 插入
        if not McPASTCR_DB.find_one():
            df = pd.read_csv("./db/McPAS-TCR.csv",low_memory=False)
            McPASTCR_DB.insert_many(df.to_dict(orient="records"))
    except Exception as e:
        print(e)
        logger.info(f"insert_db {str(e)}")
    finally:
        client.close()


def db_alignment(projectName: str) -> None:
    """
    执行指定项目的数据库比对分析。
    """
    try:
        insert_db()
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        project_db = client[PROJECT_DB_NAME]
        DB_db  = client[DB_DB_NAME]
        projectName_db = client[projectName]
        project_collection = project_db[PROJECT_COLLECTION_NAME]
        sample_collection = projectName_db[PROJECT_DATAPOINT_COLLECTION_NAME]
        pro_id = project_collection.find({'name': projectName})[0]["id"]
        document = sample_collection.find({'project_id': pro_id})
        documents_list = list(document)
        df = pd.DataFrame(documents_list)
        df = df.iloc[:, 1:]
        # Category = ["group1"]
        # index = 2
        # data_split_point_over2 = "group" + str(index)
        # while data_split_point_over2 in db.columns:
        #     Category.append(data_split_point_over2)
        #     index = index + 1
        #     data_split_point_over2 = "group" + str(index)
        Category, index = utils.get_group_list(projectName)
        datapoint = df[Category + ["sample"]]
        VDJ_DB = pd.DataFrame(list(DB_db["VDJ_DB2"].find()))
        McPASTCR_DB = pd.DataFrame(list(DB_db["McPASTCR_DB"].find()))
        CHAIN_TYPES = ["IGH", "IGL", "IGK", "TRA", "TRB", "TRG", "TRD"]
        all_path = []
        sample_df = df["sample"]
        for sample_name in sample_df:
            for file_type in CHAIN_TYPES:
                collection_name = sample_name + "__" + file_type + "_" + projectName
                E0_1_B_IGH_Mouse_Excerise = projectName_db[collection_name]
                df = pd.DataFrame(list(E0_1_B_IGH_Mouse_Excerise.find()))
                data_list = []
                if not df.empty:
                    data_list = data_list + [df, sample_name, file_type, VDJ_DB, McPASTCR_DB, projectName]
                    all_path.append(data_list)

        Alignment.start_func(datapoint, Category, all_path)
    except Exception as e:
        # print(e)
        logger.error(f"{projectName}db_alignment func出现错误:{e}")
    finally:
        client.close()


if __name__ == '__main__':
    db_alignment("YZ_profileAll_T")
'''
datapoint  Category = ["group1","group2"]  all_path [[df1,sample,chain,VDJ_DB, McPASTCR_DB],[df2,sample,chain，VDJ_DB, McPASTCR_DB]
,[df3,sample,chain，VDJ_DB, McPASTCR_DB]]  VDJ_DB McPASTCR_DB
'''
