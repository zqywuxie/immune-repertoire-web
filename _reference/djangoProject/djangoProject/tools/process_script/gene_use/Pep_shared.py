#  -*- coding:utf-8 -*-
import os
import pandas as pd
import numpy as np
import pymongo
from appone.constant import DBURL,PROJECT_DATAPOINT_COLLECTION_NAME
import shutil
from  djangoProject.tools.process_func import  utils
import warnings
from typing import Tuple, List, Any

warnings.filterwarnings("ignore", category=FutureWarning)
index_choice = False

list_index = ["21d","3M","8M","15M"]


# for dirname,dirs,filenames in os.walk("./artificial_peps"):
#     for filename in filenames:
#         for chain in ["IGH","IGK","IGL","TRA","TRB","TRD","TRG"]:
#             save_path = "./artificial_peps/"+chain
#             if not os.path.exists(save_path) :
#                 os.makedirs(save_path)
#             if chain in filename:
#                 shutil.move(os.path.join(dirname,filename),save_path)
#                 break



# organ_irdict = {}
# count = -1
# for dirname,dirs,filenames in os.walk("./pep_data"):
#
#
#     if count == -1:
#         count+=1
#         for dir_file in dirs:
#             organ_irdict[dir_file] = []
#         continue
#     for filename in filenames:
#         organ_irdict[dirname.split("/")[-1]].append(os.path.join(dirname,filename))


def dircheck(path: str) -> None:
    """
    检查目录是否存在，不存在则创建。
    """
    pep_shared_save_path=path
    if not os.path.exists(pep_shared_save_path): 
        os.makedirs(pep_shared_save_path)

def calculate(item: Tuple[str, List[str]]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    计算并保存肽段共享数据以及基因使用频率数据。
    """
    df_all = pd.DataFrame(columns=["CDR3(pep)"])
    df_gb_all_v = pd.DataFrame(columns=["V"])
    df_n_all_v = pd.DataFrame(columns=["V"])
    df_gb_all_j = pd.DataFrame(columns=["J"])
    df_n_all_j = pd.DataFrame(columns=["J"])
    df_gb_all_vj = pd.DataFrame(columns=["vj"])
    df_n_all_vj = pd.DataFrame(columns=["vj"])
    if index_choice:
        for age in list_index:
            for file_path in item[1]:
                param_col =os.path.split(file_path)[1]
                if age in file_path:
                    df = pd.read_csv(file_path,encoding='utf-8')
                
                    df_gb = df[["V","copy"]].groupby("V").sum()
                    df_gb["copy"] = df_gb["copy"]/df_gb["copy"].sum()
                    df_gb.rename(columns={'copy':param_col},inplace=True) 
                    df_gb_all_v = pd.merge(df_gb_all_v,df_gb,how='outer',on='V')

                    se_n = df["V"].value_counts(normalize=True)
                    df_n = pd.DataFrame(data={"V":se_n.index,param_col:se_n.values})
                    df_n_all_v = pd.merge(df_n_all_v,df_n,how='outer',on='V')

                    df_gb_j = df[["J","copy"]].groupby("J").sum()
                    df_gb_j["copy"] = df_gb_j["copy"]/df_gb_j["copy"].sum()
                    df_gb_j.rename(columns={'copy':param_col},inplace=True) 
                    df_gb_all_j = pd.merge(df_gb_all_j,df_gb_j,how='outer',on='J')

                    se_n_j = df["J"].value_counts(normalize=True)
                    df_n_j = pd.DataFrame(data={"J":se_n_j.index,param_col:se_n_j.values})
                    df_n_all_j = pd.merge(df_n_all_j,df_n_j,how='outer',on='J')

    
                    se_vjcombin = df["V"]+";"+df["J"]
                    se_copy = df["copy"]
                    df_vj_combine = pd.DataFrame({"vj":se_vjcombin.tolist(),"copy":se_copy.tolist()})

                    df_gb_vj = df_vj_combine[["vj","copy"]].groupby("vj").sum()
                    df_gb_vj["copy"] = df_gb_vj["copy"]/df_gb_vj["copy"].sum()
                    df_gb_vj.rename(columns={'copy':param_col},inplace=True) 
                    df_gb_all_vj = pd.merge(df_gb_all_vj,df_gb_vj,how='outer',on='vj')

                    se_n_vj = df_vj_combine["vj"].value_counts(normalize=True)
                    df_n_vj = pd.DataFrame(data={"vj":se_n_vj.index,param_col:se_n_vj.values})
                    df_n_all_vj = pd.merge(df_n_all_vj,df_n_vj,how='outer',on='vj')

                    df.rename(columns={'copy':param_col},inplace=True)    
                    concat_df = df[["CDR3(pep)",param_col]].groupby("CDR3(pep)").sum()
                    df_all = pd.merge(df_all,concat_df,how='outer',on='CDR3(pep)')


        category = {}
        for cate in df_all.columns.tolist():
            for index in list_index:
                if index in cate:
                    category[cate] = [index]
        insert_df = pd.DataFrame(category)
        insert_df.index=["category"]
        df_all = pd.concat([insert_df,df_all])
    else:
        projectName = item[1][0].split("__")[1][4:]
        # print(projectName,item)
        from appone.constant import PROJECT_FILE
        PROJECT_FILE = PROJECT_FILE+fr"/{projectName}/gene_usage"
        # PROJECT_FILE = rf"E:/Program Files/PycharmProjects/djangoProject/djangoProject/tools/process_script/{projectName}/gene_usage"
        # print(123)
        for file_path in item[1]:   #item[1]  {'TRB': ['E0_1_B__TRB_Mouse_Excerise', 'E0_2_B__TRB_Mouse_Excerise',
            param_col = file_path
            try:
                client = pymongo.MongoClient(DBURL, maxidletimems=120000)
                db = client[projectName]
                collection = db[file_path]
                fields = {"CDR3(pep)": 1, 'V': 1, 'J': 1, 'copy': 1}
                results = list(collection.find({}, fields))
                df = pd.DataFrame(results)

                # db = pd.read_csv(file_path,usecols=["CDR3(pep)","V","J","copy"])
                type_dict = {"CDR3(pep)":str,"V":str,"J":str,"copy":np.int32}
                df.astype(type_dict)
                df_gb = df[["V","copy"]].groupby("V").sum()
                df_gb["copy"] = df_gb["copy"]/df_gb["copy"].sum()
                df_gb.rename(columns={'copy':param_col},inplace=True) 
                df_gb_all_v = pd.merge(df_gb_all_v,df_gb,how='outer',on='V')

                se_n = df["V"].value_counts(normalize=True)
                df_n = pd.DataFrame(data={"V":se_n.index,param_col:se_n.values})
                df_n_all_v = pd.merge(df_n_all_v,df_n,how='outer',on='V')

                df_gb_j = df[["J","copy"]].groupby("J").sum()
                df_gb_j["copy"] = df_gb_j["copy"]/df_gb_j["copy"].sum()
                df_gb_j.rename(columns={'copy':param_col},inplace=True) 
                df_gb_all_j = pd.merge(df_gb_all_j,df_gb_j,how='outer',on='J')

                se_n = df["J"].value_counts(normalize=True)
                df_n_j = pd.DataFrame(data={"J":se_n.index,param_col:se_n.values})
                df_n_all_j = pd.merge(df_n_all_j,df_n_j,how='outer',on='J')

                se_vjcombin = df["V"]+";"+df["J"]
                se_copy = df["copy"]
                df_vj_combine = pd.DataFrame({"vj":se_vjcombin.tolist(),"copy":se_copy.tolist()})
                
                df_gb_vj = df_vj_combine[["vj","copy"]].groupby("vj").sum()
                df_gb_vj["copy"] = df_gb_vj["copy"]/df_gb_vj["copy"].sum()
                df_gb_vj.rename(columns={'copy':param_col},inplace=True) 
                df_gb_all_vj = pd.merge(df_gb_all_vj,df_gb_vj,how='outer',on='vj')

                se_n_vj = df_vj_combine["vj"].value_counts(normalize=True)
                df_n_vj = pd.DataFrame(data={"vj":se_n_vj.index,param_col:se_n_vj.values})
                df_n_all_vj = pd.merge(df_n_all_vj,df_n_vj,how='outer',on='vj')

                df.rename(columns={'copy':param_col},inplace=True)    
                concat_df = df[["CDR3(pep)",param_col]].groupby("CDR3(pep)").sum()
                df_all = pd.merge(df_all,concat_df,how='outer',on='CDR3(pep)')
            except:
                print(file_path,"pep_shared出错")


    pep_shared_save_path=PROJECT_FILE+"/Pep_shared"
    dircheck(pep_shared_save_path)

    df_all.to_csv(pep_shared_save_path+"/"+item[0]+".csv",index=False)

    collection_name = db[f"{projectName}_{item[0]}_Pep_shared"]
    collection_name.insert_many(df_all.to_dict(orient="records"))
    client.close()
    # utils.data_save_to_db(data,"Pep_shared")


    df_gb_all_v_save_path = PROJECT_FILE+"/usage/1Vusage"
    dircheck(df_gb_all_v_save_path)
    df_gb_all_v.index = df_gb_all_v["V"].tolist()
    df_gb_all_v = df_gb_all_v.drop(columns="V").T
    # print(df_gb_all_v)
    df_gb_all_v.to_csv(df_gb_all_v_save_path+"/"+item[0]+".csv",index=True)

    df_gb_all_j_save_path = PROJECT_FILE+"/usage/1Jusage"
    dircheck(df_gb_all_j_save_path)
    df_gb_all_j.index=df_gb_all_j["J"].tolist()
    df_gb_all_j = df_gb_all_j.drop(columns="J").T
    df_gb_all_j.to_csv(df_gb_all_j_save_path+"/"+item[0]+".csv",index=True)


    df_n_all_v_save_path =PROJECT_FILE+ "/usage/0Vusage"
    dircheck(df_n_all_v_save_path)
    df_n_all_v.index = df_n_all_v["V"].tolist()
    df_n_all_v = df_n_all_v.drop(columns="V").T
    df_n_all_v.to_csv(df_n_all_v_save_path+"/"+item[0]+".csv",index=True)

    df_n_all_j_save_path = PROJECT_FILE+"/usage/0Jusage"
    dircheck(df_n_all_j_save_path)
    df_n_all_j.index = df_n_all_j["J"].tolist()
    df_n_all_j = df_n_all_j.drop(columns="J").T
    df_n_all_j.to_csv(df_n_all_j_save_path+"/"+item[0]+".csv",index=True)

    df_n_all_vj_save_path = PROJECT_FILE+"/usage/0VJusage"
    dircheck(df_n_all_vj_save_path)
    df_n_all_vj.index = df_n_all_vj["vj"].tolist()
    df_n_all_vj = df_n_all_vj.drop(columns="vj").T
    df_n_all_vj.to_csv(df_n_all_vj_save_path+"/"+item[0]+".csv",index=True)

    df_gb_all_vj_save_path = PROJECT_FILE+"/usage/1VJusage"
    dircheck(df_gb_all_vj_save_path)
    df_gb_all_vj.index = df_gb_all_vj["vj"].tolist()
    df_gb_all_vj = df_gb_all_vj.drop(columns="vj").T
    # print(df_gb_all_vj)
    df_gb_all_vj.to_csv(df_gb_all_vj_save_path+"/"+item[0]+".csv",index=True)


    return df_all,df_gb_all_v,df_n_all_v
    

from concurrent.futures import *
from multiprocessing import cpu_count

core_num = cpu_count()



def start_func(organ_irdict2: dict, projectName2: str) -> None:
    """
    启动并行化的肽段共享和基因使用计算流程。
    """
    with ProcessPoolExecutor(max_workers=core_num) as executor:
        results = executor.map(calculate,organ_irdict2.items())


# if __name__ :
#
#     with ProcessPoolExecutor(max_workers=core_num) as executor:
#         results = executor.map(calculate,organ_irdict.items())

# for item in organ_irdict.items():
#     calculate(item)


# if __name__ == '__main__':
#     from appone.constant import PROJECT_FILE
#     aaaa = r"./static/files"
#     PROJECT_FILE = aaaa + fr"/mou/gene_usage"
#     for item in os.listdir(PROJECT_FILE):
#         print(item)