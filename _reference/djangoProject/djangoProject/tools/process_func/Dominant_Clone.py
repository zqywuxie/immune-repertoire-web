import pymongo
from appone.constant import DBURL, CHAIN_TYPES
from djangoProject.tools.process_script.Dominant_Clone import Dominant_Clone
from djangoProject.tools.process_func import utils
import pandas as pd
from djangoProject.tools.logger import log
logger = log.GetLogger().get_logger()
"[[db,sample,chain,top_x],[db,sample,chain,top_x]]"


def Dominant_Clone_func(projectName: str) -> None:
    """
    分析指定项目中的优势克隆。
    """
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        db = client[projectName]
        datapoint = utils.get_datapoint_df(projectName, db)
        data_list = []
        for file_type in CHAIN_TYPES:
            for index, row in datapoint.iterrows():
                coll_name = db[row["sample"] + "__" + file_type + "_" + projectName]
                if coll_name.count_documents({}) != 0:
                    document = coll_name.find()
                    df = pd.DataFrame(list(document))
                    data = [df, row["sample"], file_type]
                    data_list.append(data)
        category, index = utils.get_group_list(projectName)
        
        Dominant_Clone.start_func(projectName, data_list, datapoint, category)
    except Exception as e:
        # print(e)
        logger.error(f"{projectName}Dominant_Clone_func func出现错误:{e}")
    finally:

        client.close()

if __name__ == '__main__':
    Dominant_Clone_func("mou")
