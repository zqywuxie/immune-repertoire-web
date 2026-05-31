import pandas as pd
import os
import numpy as np
from itertools import combinations
import copy

TS = 4

file_path = "./Pep_shared_cate"
Csv_path = []
for root,path,filenames in os.walk(file_path):
    for filename in filenames:
        Csv_path.append(os.path.join(root,filename))



def arrage(file_path):
    df = pd.read_csv(file_path,low_memory=False)
    df.fillna(0,inplace=True)
    category_dict = {}
    for cate,idname in zip(df.iloc[0].tolist()[1:],df.iloc[0].index[1:].to_list()):
        if cate not in category_dict.keys():
            category_dict[cate] = [idname]
        else:
            category_dict[cate].append(idname)
    df_nocate = df.drop(labels=0,axis=0)
    for cate,idnames in category_dict.items():
        ca = np.array(df_nocate[idnames].values,dtype=np.float32).astype(np.int32)
        df[cate+"__sum"]= [" "]+ca.sum(axis=1).tolist()
        ca[ca>=1]=1
        df[cate+"__count"] = [" "]+ ca.sum(axis=1).tolist()
    count_name_list = []
    threash_count = TS
    for column in df.columns.to_list():
        if column.find("count") != -1:
            count_name_list.append(column)
    all_num = np.sum(np.array(df[count_name_list].iloc[1:].values,dtype=np.float32).astype(np.int32),axis=1).tolist()
    all_num.insert(0," ")
    df["all_num"] = all_num
    df_sort = df.iloc[1:].sort_values(by="all_num",axis=0,  ascending=False, inplace=False, kind='quicksort', na_position='last')
    df_sort = df_sort[df_sort["all_num"]>threash_count]
    cb_list = []
    category_list = []
    for i  in range(len(count_name_list)+1)[2:]:
        cb_list+=list(combinations(count_name_list,i))
    cb_list = count_name_list+cb_list
    # cb_list = cb_list[:-1]
    proportion_dict = {} 
    df_t = pd.DataFrame(columns=df_sort.columns)
    for cb in cb_list:
        other_list = copy.deepcopy(count_name_list)
        if type(cb) == str:
            other_list.remove(cb)
            df_m = df_sort[df_sort[cb]!=0]
            for remove_type in other_list:
                df_m = df_m[df_m[remove_type]==0]
            pre_num = df_m.shape[0]
            proportion_dict[cb] = pre_num
            category_list += pre_num*[cb]
            df_t = pd.concat([df_t,df_m])
            continue
        df_m = df_sort
        for item in cb:
            other_list.remove(item)
        for item in cb:
            df_m = df_m[df_m[item]!=0]
        for item in other_list:
            df_m = df_m[df_m[item]==0]
        pre_num = df_m.shape[0]
        proportion_dict[cb] = pre_num
        category_list += pre_num*[cb]
        df_t = pd.concat(
            [df_t,df_m])
    df_t["category"] = category_list
    df_top = pd.DataFrame(df.iloc[0]).T
    df_top["category"] = " "
    df_t = pd.concat([df_top,df_t])
    arrage_path = "arrage_pep"
    dir = os.path.split(file_path)
    save_path = os.path.join(arrage_path,dir[0])
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    df_t.to_csv(os.path.join(save_path,dir[1]),index=False)
    sum_value = 0
    for key,value in proportion_dict.items():
        sum_value += value
    for key,value in proportion_dict.items():
        if sum_value == 0:
            proportion_dict[key] = 0
        else:
            proportion_dict[key] = value/sum_value
    prop_dict ={}
    prop_dict["cate"] = list(proportion_dict.keys())
    prop_dict["prop"] = list(proportion_dict.values())
    df_prop = pd.DataFrame(prop_dict)
    # df_prop.sort_values(by="prop",inplace=True)
    prop_path = "prop_pep"
    dir = os.path.split(file_path)
    save_path = os.path.join(prop_path,dir[0])
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    df_prop.to_csv(os.path.join(save_path,dir[1]),index=False)


# from concurrent.futures import *
# from multiprocessing import cpu_count

# core_num = cpu_count()
# if __name__ == '__main__':
#     with ProcessPoolExecutor(max_workers=core_num) as executor:
#             results = executor.map(arrage,Csv_path)

for file_path in Csv_path:
    arrage(file_path)
