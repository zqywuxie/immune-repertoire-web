import shutil
import time
import os
import portalocker
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore, register_job

from appone import mongodb_client_factory
from djangoProject.settings import MY_GLOBAL_List
from djangoProject.tools.process_func import boxplot_func, gene_usage, umap_func, db_alignment, topClone_func, \
    CDR3_length, ECDF_func, Dominant_Clone, Similar_Clone
from djangoProject.tools.logger.log import GetLogger

logger = GetLogger.get_logger()


def all_fun(projectName):
    boxplot_func.boxplot_func(projectName)
    gene_usage.gene_usage(projectName)
    umap_func.umap_func(projectName)
    db_alignment.db_alignment(projectName)
    topClone_func.topClone_func(projectName)
    CDR3_length.get_cdr3_length(projectName)
    ECDF_func.ECDF_func(projectName)
    Dominant_Clone.Dominant_Clone_func(projectName)
    Similar_Clone.Similar_Clone_func(projectName)


# @register_job(scheduler, 'interval', id='test', seconds=30, args=[], replace_existing=True)
def test():
    from appone.constant import PROJECT_LIST
    import json
    with open(PROJECT_LIST, "r+") as f:
        dict_b = json.load(f)
    if len(dict_b["project_list"]) == 0:
        logger.info(f"List is empty")
        return None
    projectName = dict_b["project_list"][0]
    dict_b["project_list"].pop(0)
    with open(PROJECT_LIST, "w") as outfile:
        json.dump(dict_b, outfile)
    logger.info(f"开始处理 {projectName}")
    all_fun(projectName)
    logger.info(f"处理 {projectName} 完成")
    from appone.constant import PROJECT_DB_NAME, PROJECT_COLLECTION_NAME
    with mongodb_client_factory() as client:
        db = client[PROJECT_DB_NAME]
        project_collection = db[PROJECT_COLLECTION_NAME]
        project_collection.update_one({"name": projectName}, {"$set": {"is_processed": "True"}})



def rm_dir():
    from djangoProject.settings import TAR_DIR
    dirs = os.listdir(TAR_DIR)
    for _dir in dirs:
        path = os.path.join(TAR_DIR, _dir)
        _time = os.path.getmtime(path)
        now = time.time()
        if now - _time > 10 * 60 * 60:
            if os.path.isdir(path):
                shutil.rmtree(path)
                print(f"删除文件夹 {path}")
            else:
                os.remove(path)
                print(f"删除文件 {path}")


def initscheduler():
    lock_file_path = "scheduler.lock"
    try:
        f = open(lock_file_path, "wb")
        portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
        print("initscheduler (cross-platform)..........")
        # 实例化调度器
        scheduler = BackgroundScheduler()
        # 调度器使用默认的DjangoJobStore()
        scheduler.add_jobstore(DjangoJobStore(), 'default')
        scheduler.add_job(test, 'interval', id='test', seconds=60, args=[], replace_existing=True)
        scheduler.add_job(rm_dir, 'cron', id='rm_dir', hour=4, minute=0, second=0, args=[], replace_existing=True)
        # 5秒循环执行
        scheduler.start()
    except portalocker.exceptions.LockException as e:
        logger.info(f"Failed to acquire lock: {e}")
        pass
        return

    def unlock():
        portalocker.unlock(f)
        scheduler.shutdown()
        f.close()

    atexit.register(unlock)

#
