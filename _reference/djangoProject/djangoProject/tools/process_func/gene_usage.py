import os
import shutil

from djangoProject.tools.process_script.gene_use import Pep_shared, add_cate_usage, gene, Heat_map_Thread, \
    add_cate_shared, Pep_statistication, CDR3_arrage_heatmap_ver1_0,volcano_plot
import pymongo
from appone.constant import DBURL,PROJECT_DATAPOINT_COLLECTION_NAME
import pandas as pd
from djangoProject.tools.process_func import utils
from djangoProject.tools.logger import log
logger = log.GetLogger().get_logger()
def gene_usage(projectName: str) -> None:
    """
    分析并处理指定项目的基因使用情况（Gene Usage）。
    """
    try:
        CHAIN_TYPES = ["IGH", "IGL", "IGK", "TRA", "TRB", "TRG", "TRD"]
        organ_irdict2 = {}
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        db = client[projectName]
        # project_collection = db['project']
        sample_collection = db[PROJECT_DATAPOINT_COLLECTION_NAME]
        groupSpecification_collection = db['groupSpecification']
        document = sample_collection.find({}, {"_id": 0})
        documents_list = list(document)
        df = pd.DataFrame(documents_list)
        category, index = utils.get_group_list(projectName)
        df = df[["sample"]+category]
        sample_names_list = pd.DataFrame(documents_list)["sample"].tolist()
        for file_type in CHAIN_TYPES:
            organ_irdict2[file_type] = []
            for sample_name in sample_names_list:
                collection_name = sample_name + "__" + file_type + "_" + projectName
                E0_1_B_IGH_Mouse_Excerise = db[collection_name]
                if E0_1_B_IGH_Mouse_Excerise.count_documents({}) > 0:
                    organ_irdict2[file_type].append(collection_name)
        # 判断organ_irdict2 空的部分，把空的部分删除
        for file_type in CHAIN_TYPES:
            if len(organ_irdict2[file_type]) == 0:
                del organ_irdict2[file_type]

        Pep_shared.start_func(organ_irdict2, projectName)
        # 添加分组
        arrange_dict = groupSpecification_collection.find({'name': projectName})[0]["groupSpecification"]
        for Group in arrange_dict:
            datapoint_df = pd.DataFrame(list(sample_collection.find()))
            datapoint_df = datapoint_df.iloc[:, 1:]
            # print(Group, arrange_dict[Group])
            add_cate_usage.start_func(Group, arrange_dict[Group], projectName, dp_df=datapoint_df)
        # add_cate_shared.start_func(projectName, arrange_dict,df)
        # 画图
        Heat_map_Thread.start_func(projectName)
        gene.start_func(projectName)

        # pep_shared   CDR3 share
        add_cate_shared.start_func(projectName, arrange_dict, df)
        Pep_statistication.start_func(projectName)
        CDR3_arrage_heatmap_ver1_0.start_func(projectName)

        volcano_plot.start_func(projectName)
    except Exception as e:
        # print(e)
        logger.error(f"{projectName}的gene_usage 出现错误 {e}")
    finally:
        # 删除 usage这个文件夹
        from appone.constant import PROJECT_FILE
        PROJECT_FILE = PROJECT_FILE + fr"/{projectName}/gene_usage"
        delete_file = PROJECT_FILE + "/usage"
        delete_file2 = PROJECT_FILE + "/usage_cate"
        if os.path.exists(delete_file):
            logger.info(f"{projectName}删除usage文件夹")
            shutil.rmtree(delete_file)
        else:
            logger.info(f"{projectName}usage文件夹不存在")
        # for dirname,dirs,filenames in os.walk(delete_file2):
        #     for filename in filenames:
        #         if filename.endswith(".csv"):
        #             filepath = os.path.join(delete_file2,filename)
        #             if os.path.exists(filepath):
        #                 os.remove(filepath)
        #                 print(f"删除csv文件{filename}")
        client.close()

if __name__ == '__main__':
    gene_usage("6_4")

