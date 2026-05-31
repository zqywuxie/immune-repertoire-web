import pandas as pd
import pymongo
from appone.constant import DBURL, PROJECT_DB_NAME, PROJECT_COLLECTION_NAME, PROJECT_DATAPOINT_COLLECTION_NAME
from djangoProject.tools.process_script.CDR3_length import CDR3_length
from djangoProject.tools.process_func import utils
from djangoProject.tools.logger import log

logger = log.GetLogger().get_logger()


# {
#     "IGH":[["df1","sample_name"],"df2"]
# }
def get_cdr3_length(projectName: str) -> None:
    """
    计算并处理指定项目的 CDR3 长度分布。
    """
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        projectName_db = client[projectName]
        df = utils.get_datapoint_df(projectName, projectName_db)
        df = df.iloc[:, 1:]
        datapoint = df
        # print("db",db.columns.tolist())
        category, index = utils.get_group_list(projectName)
        # print(category)
        CHAIN_TYPES = ["IGH", "IGL", "IGK", "TRA", "TRB", "TRG", "TRD"]
        chain2file = {}
        sample_df = df["sample"]
        for file_type in CHAIN_TYPES:
            data_list = []
            for sample_name in sample_df:
                collection_name = sample_name + "__" + file_type + "_" + projectName
                E0_1_B_IGH_Mouse_Excerise = projectName_db[collection_name]
                df = pd.DataFrame(list(E0_1_B_IGH_Mouse_Excerise.find()))
                if not df.empty:
                    data = [df, sample_name]
                    data_list.append(data)
            if data_list:
                chain2file[file_type] = data_list
        # print(datapoint)
        CDR3_length.start_func(chain2file, category, datapoint, projectName)
    except Exception as e:
        # print(e)
        logger.error(f"{projectName}get_cdr3_length func出现错误:{e}")
    finally:
        client.close()


if __name__ == '__main__':
    get_cdr3_length("25_4_26")
