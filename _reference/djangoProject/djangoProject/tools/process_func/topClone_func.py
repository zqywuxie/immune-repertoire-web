from appone.constant import DBURL, PROJECT_COLLECTION_NAME, PROJECT_DB_NAME, PROJECT_DATAPOINT_COLLECTION_NAME
from appone.constant import CHAIN_TYPES
import pymongo
import pandas as pd
from djangoProject.tools.process_script.topClone import topClone
from djangoProject.tools.process_func import utils
from djangoProject.tools.logger import log

logger = log.GetLogger().get_logger()


def topClone_func(projectName: str) -> None:
    """
    分析并处理指定项目中的 Top Clone。
    """
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        project_db = client[PROJECT_DB_NAME]
        projectName_db = client[projectName]
        project_collection = project_db[PROJECT_COLLECTION_NAME]
        sample_collection = projectName_db[PROJECT_DATAPOINT_COLLECTION_NAME]
        pro_id = project_collection.find({'name': projectName})[0]["id"]
        document = sample_collection.find({'project_id': pro_id})
        documents_list = list(document)
        df = pd.DataFrame(documents_list)
        Category, index = utils.get_group_list(projectName)
        group_list = ["sample"] + Category
        datapoint = df[group_list]
        param_dict = {}
        for file_type in CHAIN_TYPES:
            if file_type not in param_dict:
                param_dict[file_type] = {}
            for sample in datapoint["sample"]:
                collection_name = sample + "__" + file_type + "_" + projectName
                E0_1_B__IGH_Mouse_Excerise = projectName_db[collection_name]
                df = pd.DataFrame(list(E0_1_B__IGH_Mouse_Excerise.find()))
                if not df.empty:
                    if sample not in param_dict[file_type]:
                        param_dict[file_type][sample] = df
            # 使用字典推导式来过滤掉值为空字典的项
        param_dict = {key: value for key, value in param_dict.items() if value != {}}
        # print(param_dict)
        logger.info(f"用字典推导式来过滤掉值为空字典的项{projectName},keys:{param_dict.keys()}")
        logger.info(f"用字典推导式来过滤掉值为空字典的项{projectName},keys:{param_dict.keys()}")
        logger.info(f"用字典推导式来过滤掉值为空字典的项{projectName},keys:{param_dict.keys()}")
        topClone.start_func(param_dict, datapoint, projectName)
    except Exception as e:
        # print(e)
        logger.error(f"{projectName}topClone func出现错误:{e}")
    finally:
        client.close()


if __name__ == '__main__':
    topClone_func("6_4")
