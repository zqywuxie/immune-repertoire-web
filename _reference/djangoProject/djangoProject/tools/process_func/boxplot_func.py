from djangoProject.tools.process_script.boxplot.BoxPlot_1120_Thread_Arrange import start_func
from appone.constant import DBURL,PROJECT_DB_NAME,PROJECT_COLLECTION_NAME,PROJECT_DATAPOINT_COLLECTION_NAME
import pymongo
import pandas as pd
from djangoProject.tools.process_func import utils
from djangoProject.tools.logger import log
logger = log.GetLogger().get_logger()
def boxplot_func(projectName: str, is_p_value_flag2: bool = True) -> None:
    """
    为指定项目生成箱线图分析。
    """
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        project_db = client[PROJECT_DB_NAME]
        projectName_db = client[projectName]
        project_collection = project_db[PROJECT_COLLECTION_NAME]
        sample_collection = projectName_db[PROJECT_DATAPOINT_COLLECTION_NAME]
        groupSpecification_collection = projectName_db['groupSpecification']
        pro_id = project_collection.find({'name': projectName})[0]["id"]
        document = sample_collection.find({'project_id': pro_id},{"project_id":0})
        documents_list = list(document)
        df = pd.DataFrame(documents_list)
        df = df.iloc[:, 1:]
        arrange_dict = groupSpecification_collection.find({'name': projectName})[0]["groupSpecification"]
        Category,index = utils.get_group_list(projectName)
        data_split_point_begin2 = Category[0]
        data_split_point_over2 = Category[-1]
        from appone.constant import PROFILE_BOXPLOT_DIRNAME
        df = utils.remove_sample_col(df)
        start_func(df, arrange_dict, projectName, data_split_point_begin2, data_split_point_over2,
                   is_p_value_flag2, PROFILE_BOXPLOT_DIRNAME,param_begin2 ="TRA_percent_reads_all",param_over2=df.columns[-1])
    except Exception as e:
        logger.error(f"{projectName}profile_boxplot func出现错误:{e}")
    finally:
        client.close()

if __name__ == '__main__':
    boxplot_func("6_4")
