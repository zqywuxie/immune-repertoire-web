import pandas as pd
import os
import numpy as np

datapoint_path = "Profile_All.csv"
list_sorted = ["before","after"]
Group = "therapy" #essential
dp_df = pd.read_csv(datapoint_path)
remove_list = [np.nan]

VJusage_paths = []
for dirname,dirs,filenames in os.walk("./usage/"):
    for filename in filenames:
        VJusage_paths.append(os.path.join(dirname,filename))


for file_path in VJusage_paths:
    df = pd.read_csv(file_path)
    vj_cate = []
    use_file = []
    for name_vj in df[df.columns[0]]:
        for name_dp in dp_df[dp_df.columns[0]]:
            pep_name_split = name_vj.split("__")
            samplename = ""
            for str_split in pep_name_split[:-1]:
                samplename = samplename+str_split+"__"
            samplename = samplename[:-2]
            print(samplename)
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
    save_path = "./usage_cate/"
    dir = os.path.split(file_path)
    save_path = os.path.join(save_path,dir[0])
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    df_s.rename(columns={"Unnamed: 0":"sample"},inplace=True)
    df_s.to_csv(os.path.join(save_path,dir[1]),index=False)