import pymongo
import pandas as pd
from djangoProject.tools.process_script.Similar_Clone import Similar_Clone
from appone.constant import DBURL, CHAIN_TYPES, PROJECT_DATAPOINT_COLLECTION_NAME, PROJECT_DB_NAME, \
    PROJECT_COLLECTION_NAME



def Similar_Clone_func(projectName: str) -> None:
    """
    分析指定项目中的相似克隆。
    """
    pep_files_dict = {}
    client = pymongo.MongoClient(DBURL, maxidletimems=12000)
    db = client[projectName]
    pro_id = client[PROJECT_DB_NAME][PROJECT_COLLECTION_NAME].find({'name': projectName})[0]["id"]
    datapoint_df = pd.DataFrame(list(db[PROJECT_DATAPOINT_COLLECTION_NAME].find({'project_id': pro_id})))
    sample_names = datapoint_df["sample"].tolist()
    group_list = list(db["groupSpecification"].find({'name': projectName})[0]["groupSpecification"].keys())
    for chain in CHAIN_TYPES:
        pep_files_dict[chain] = {}
        for sample_name in sample_names:
            collection_name = sample_name + "__" + chain + "_" + projectName
            pep_file_collection = db[collection_name]
            if pep_file_collection.count_documents({}) > 0:
                pep_files_dict[chain][sample_name] = pep_file_collection
    for chain in CHAIN_TYPES:
        if len(pep_files_dict[chain]) == 0:
            del pep_files_dict[chain]
    # print(pep_files_dict.keys())
    Similar_Clone.start_func(projectName, pep_files_dict, group_list, datapoint_df)
    client.close()
    # volcano_dict

if __name__ == '__main__':
    Similar_Clone_func("25_4_26")

