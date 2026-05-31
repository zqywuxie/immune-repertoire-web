# import logging
import os
from datetime import datetime
from djangoProject.settings import LOG_DIR
# 导包
import logging.handlers
import threading

lock = threading.Lock()
class GetLogger:
    logger = None

    @classmethod
    def get_logger(cls):
        if cls.logger is None:
            with lock:
                if cls.logger is None:
                    date = datetime.now().strftime('%Y-%m-%d')
                    if not os.path.exists(LOG_DIR):
                        os.mkdir(LOG_DIR)
                    file_path = LOG_DIR / f"app_{date}.log"
                    # 获取 日志器
                    cls.logger = logging.getLogger()
                    # 设置 日志器 级别
                    cls.logger.setLevel(logging.INFO)

                    # 获取处理器 控制台
                    sh = logging.StreamHandler()
                    # 获取处理器 文件-以时间分隔
                    th = logging.handlers.TimedRotatingFileHandler(filename=file_path,
                                                                   when="D",
                                                                   interval=1,
                                                                   backupCount=7,
                                                                   encoding="utf-8")
                    # 设置格式器
                    fmt = "%(asctime)s %(levelname)s [%(name)s] [%(filename)s (%(funcName)s:%(lineno)d] - %(message)s"
                    fm = logging.Formatter(fmt)
                    # 将格式器添加到 处理器 控制台
                    sh.setFormatter(fm)
                    # 将格式器添加到 处理器 文件
                    th.setFormatter(fm)
                    # 将处理器添加到 日志器
                    cls.logger.addHandler(sh)
                    cls.logger.addHandler(th)
        return cls.logger


if __name__ == '__main__':
    logger = GetLogger().get_logger()
    logger.info("info信息被执行")
    logger.error("error信息被执行")
#
# def init_log():
#     date = datetime.now().strftime('%Y-%m-%d')
#     logger = logging.getLogger()# 初始化日志器对象
#     logger.setLevel(logging.INFO) #设置日志器等级
#     #获取控制台处理器
#
#     BASE_DIR = os.path.dirname(__file__)
#     file_name = BASE_DIR+f"/log/log_{date}.log"
#     #获取文件处理器
#     handel = logging.FileHandler(file_name,encoding="utf-8")
#     # 定义格式化器
#     fmt = '%(asctime)s [%(name)s] %(filename)s  %(levelname)s %(message)s'
#     formattr = logging.Formatter(fmt)
#     sh = logging.StreamHandler()
#     sh.setFormatter(formattr)
#     handel.setFormatter(formattr)
#     logger.addHandler(sh)
#     logger.addHandler(handel)
