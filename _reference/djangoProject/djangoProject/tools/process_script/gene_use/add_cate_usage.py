import pandas as pd
import os
import numpy as np
import warnings
from typing import List

warnings.filterwarnings("ignore", category=FutureWarning)

# datapoint_path = "all_data_points.csv"
# list_sorted = ["Dampness","None-Dampness"]
# Group = "Group" #essential
# dp_df = pd.read_csv(datapoint_path)
remove_list = [np.nan]

def caculate(PROJECT_FILE: str, dp_df: pd.DataFrame, Group: str, list_sorted: List[str]) -> None:
    """
    为基因使用频率数据添加分类信息并保存到 usage_cate 目录。
    """
    VJusage_paths = []
    for dirname,dirs,filenames in os.walk(PROJECT_FILE+"/usage/"):
        for filename in filenames:
            VJusage_paths.append(os.path.join(dirname,filename))
    # print("VJusage_paths",VJusage_paths)
    for file_path in VJusage_paths:
        df = pd.read_csv(file_path)
        # print("db",db)
        vj_cate = []
        use_file = []
        for name_vj in df[df.columns[0]]:
            for name_dp in dp_df[dp_df.columns[0]]:
                pep_name_split = name_vj.split("__")
                samplename = ""
                for str_split in pep_name_split[:-1]:
                    samplename = samplename+str_split+"__"
                samplename = samplename[:-2]
                # print(samplename)
                if samplename == name_dp:
                    use_file.append(name_vj)
                    vj_cate.append(dp_df[dp_df[dp_df.columns[0]]==name_dp][Group].values.tolist()[0])
                    break
        t_vj_cate = []
        t_use_file = []
        for item,filename in zip(vj_cate,use_file):
            for remove_item in remove_list:
                 if item is not remove_item:
                    t_vj_cate.append(item)
                    t_use_file.append(filename)
        vj_cate = t_vj_cate
        use_file = t_use_file
        df_s = df[df[df.columns[0]].isin(use_file)]
        df_s.insert(loc=1,column="Category",value=vj_cate)
        df_s['Category'] = df_s['Category'].astype('category').cat.set_categories(list_sorted)
        df_s.sort_values(by=['Category'], ascending=True,inplace=True)
        save_path = PROJECT_FILE+"/usage_cate/"
        dir = os.path.split(file_path)
        mid_path = dir[0].split("/")[-2]+"/"+dir[0].split("/")[-1]
        save_path = save_path+mid_path
        # print(mid_path)
        # print(dir)
        # save_path = os.path.join(save_path,dir[0])
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        df_s.rename(columns={"Unnamed: 0":"sample"},inplace=True)
        if not os.path.exists(os.path.join(save_path,Group)):
            os.makedirs(os.path.join(save_path,Group))
        # print("db-s",df_s)
        df_s = df_s.dropna(subset=['Category']) # 删除Category列为空的行
        df_s.to_csv(os.path.join(save_path,Group,dir[1]),index=False)


def start_func(Group2: str, list_sorted2: List[str], projectName2: str, dp_df: pd.DataFrame) -> None:
    """
    启动基因使用分类信息添加流程。
    """
    # global Group
    # Group = Group2
    # global list_sorted
    # list_sorted = list_sorted2
    from appone.constant import PROJECT_FILE
    PROJECT_FILE = PROJECT_FILE+fr"/{projectName2}/gene_usage"
    # PROJECT_FILE = rf"E:/Program Files/PycharmProjects/djangoProject/djangoProject/tools/process_script/{projectName2}/gene_usage"
    caculate(PROJECT_FILE,dp_df,Group2,list_sorted2)