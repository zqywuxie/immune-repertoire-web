import pandas as pd
import os
import numpy as np

datapoint_path = "Profile_All.csv"
index_sorted = ["cancer","healthy"]
Group = "disease"
dp_df = pd.read_csv(datapoint_path)


"在这里的会提前排序，没在这里面的会放到后面但是不会删除"

remove_list = [np.nan]

Pep_paths = []
for dirname,dirs,filenames in os.walk("./Pep_shared"):
    for filename in filenames:
        Pep_paths.append(os.path.join(dirname,filename))
def add_cate(file_path):
    pep_df = pd.read_csv(file_path)
    cate_dict = {'CDR3(pep)':['category']}
    # pep_cate = ["category"]
    for pep_name in pep_df[pep_df.columns[1:]]:
        for name_dp in dp_df[dp_df.columns[0]]:
            pep_name_split = pep_name.split("__")
            samplename = ""
            for str_split in pep_name_split[:-1]:
                samplename = samplename+str_split+"__"
            samplename = samplename[:-2]
            if  samplename== name_dp:
                print(name_dp,pep_name.split("__")[0])
                cate_dict[pep_name] = [dp_df[dp_df[dp_df.columns[0]]==name_dp][Group].values.tolist()[0]]
                break
    # cate_dict = {}
    # for i in range(len(pep_cate)):
    #     if type(pep_cate[i]) != str:
    #         if np.isnan(pep_cate[i]):
    #             continue
    #     cate_dict[pep_df.columns[i]] = [pep_cate[i]]
    remove_key = []
    for item in cate_dict.items():
        for key in remove_list:
            if item[1][0] is key:
                remove_key.append(item[0])
    for key in remove_key:
        cate_dict.pop(key)

    cate_df = pd.DataFrame(cate_dict)
    pep_df = pd.concat([cate_df,pep_df[list(cate_dict.keys())]])
    categorys = sorted(list(pep_df.iloc[0].unique()[1:]))
    index_sorted.reverse()
    if len(index_sorted):
        for cate in index_sorted:
            if cate in categorys:
                categorys.remove(cate)
                categorys.insert(0,cate)
    categorys.reverse()
    categorys_dict = {}
    for col in pep_df.columns[1:]:
        if pep_df[col].iloc[0]==" ":
            break
        else:
            if pep_df[col].iloc[0] not in list(categorys_dict.keys()):
                categorys_dict[pep_df[col].iloc[0]] = [col]
            else:
                categorys_dict[pep_df[col].iloc[0]].append(col)
    for category in categorys:
        for col in categorys_dict[category]:
            col_t = pep_df[col]
            pep_df.drop(columns=col,inplace=True)
            pep_df.insert(1,col,col_t)
    save_path = "./Pep_shared_cate"
    dir = os.path.split(file_path)
    save_path = os.path.join(save_path,dir[0])
    if not os.path.exists(save_path):
        os.makedirs(save_path)

    pep_df.to_csv(os.path.join(save_path,dir[1]),index=False)

from concurrent.futures import *
from multiprocessing import cpu_count

core_num = cpu_count()
if __name__ == '__main__':
    with ProcessPoolExecutor(max_workers=core_num) as executor:
            results = executor.map(add_cate,Pep_paths)

# for filepath in Pep_paths:
#     add_cate(filepath)