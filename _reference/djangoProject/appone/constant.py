import os
from djangoProject.settings import BASE_DIR, IS_DEPLOY

DBURL = os.getenv("MONGO_URI", "mongodb://localhost:27017/")  #'mongodb://localhost:27017/'
CHAIN_TYPES = ["IGH", "IGL", "IGK", "TRA", "TRB", "TRG", "TRD"]
# PROJECT_FILE = r"E:/Program Files/PycharmProjects/djangoProject/djangoProject/tools/process_script"
if IS_DEPLOY:   
    PROJECT_FILE = str(BASE_DIR / 'static' / 'files')
else:
    PROJECT_FILE = r"../static/files"

PROJECT_LIST = BASE_DIR / 'static' / 'project_list.json'
PROFILE_BOXPLOT_DIRNAME = "profile_boxplot"
TOPCLONE_DIRNAME = "topClone_boxplot"
CDR3_LENGTH_DIRNAME = "CDR3_lenth_boxplot"

# 数据库库名以及表名
PROJECT_DB_NAME = "project"  # 项目的总说明表 包括2个数据库比对的的表
PROJECT_COLLECTION_NAME = "project_detail"
PROJECT_DATAPOINT_COLLECTION_NAME = "datapoint"
DB_DB_NAME = "DB"
PROJECT_SAMPLE_DESCRIBE_COLLECTION_NAME = "sample_describe"

SAMPLE_TABLE = BASE_DIR / 'static' / 'sample_table.xlsx'
