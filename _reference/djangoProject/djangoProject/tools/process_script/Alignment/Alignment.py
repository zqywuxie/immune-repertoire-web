import shutil

import pandas as pd
import os
import parmap
import pymongo
from appone.constant import DBURL, PROJECT_FILE
import warnings
from typing import List, Tuple, Any

from djangoProject.tools.process_func import utils

warnings.filterwarnings("ignore", category=FutureWarning)
profile = "./profile.csv"
# category = "category"
# df_profile = ""  #pd.read_csv(profile)

Species = "Human"

contained_Pathology = False
use_Pathology = ["HomoSapiens"]

contained_Category_McPASTCR = False
use_Category = ["Autoimmune"]

# pep_paths = []
# for dirname,dirs,filenames in os.walk("./artificial_peps"):
#     for filename in filenames:
#         pep_paths.append(os.path.join(dirname,filename))

VDJ_Species = ""
McPASTCR_Species = ""
if Species == "Mouse":
    VDJ_Species = "MusMusculus"
    McPASTCR_Species = "Mouse"
elif Species == "Human":
    VDJ_Species = "HomoSapiens"
    McPASTCR_Species = "Human"


def alignment(path: List[Any]) -> Tuple[str, str, float, float]:
    """
    对给定的样本和链进行序列比对，计算其在 VDJdb 和 McPAS-TCR 数据库中的特异性比例。
    """
    # VDJ_DB = pd.read_csv("./DB/vdjdb.csv", low_memory=False)
    VDJ_DB = path[3]
    McPASTCR_DB = path[4]
    projectName = path[5]
    # print(f"VDJ_DB{VDJ_DB}")
    VDJ_DB["PubMed.ID"] = VDJ_DB["Reference"].astype(str)
    # McPASTCR_DB = pd.read_csv("./DB/McPAS-TCR.csv", low_memory=False)
    McPASTCR_DB["PubMed.ID"] = McPASTCR_DB["PubMed.ID"].astype(str)
    df_pep = path[0]
    # sample_pep = path.split("/")[-1]
    sample = path[1]
    chain = path[2]

    if chain not in ["TRA", "TRB"]:
        return

    if chain == "TRA":
        alignment_result_McPASTCR = McPASTCR_DB[McPASTCR_DB["CDR3.alpha.aa"].isin(df_pep["CDR3(pep)"].tolist())][
            ["CDR3.alpha.aa", "Species", "Epitope.peptide", "Pathology", "Category", "PubMed.ID"]]
        alignment_result_McPASTCR.insert(0, "CDR3(pep)", alignment_result_McPASTCR.pop("CDR3.alpha.aa"))
        alignment_result_McPASTCR = alignment_result_McPASTCR[alignment_result_McPASTCR["Species"] == McPASTCR_Species]
    else:
        alignment_result_McPASTCR = McPASTCR_DB[McPASTCR_DB["CDR3.beta.aa"].isin(df_pep["CDR3(pep)"].tolist())][
            ["CDR3.beta.aa", "Species", "Epitope.peptide", "Pathology", "Category", "PubMed.ID"]]
        alignment_result_McPASTCR.insert(0, "CDR3(pep)", alignment_result_McPASTCR.pop("CDR3.beta.aa"))
        alignment_result_McPASTCR = alignment_result_McPASTCR[alignment_result_McPASTCR["Species"] == McPASTCR_Species]

    alignment_result_VDJ = VDJ_DB[VDJ_DB["CDR3"].isin(df_pep["CDR3(pep)"].tolist())][
        ["CDR3", "Species", "Epitope", "Epitope species", "Reference"]]
    alignment_result_VDJ.insert(0, "CDR3(pep)", alignment_result_VDJ.pop("CDR3"))
    alignment_result_VDJ.insert(2, "Epitope.peptide", alignment_result_VDJ.pop("Epitope"))
    alignment_result_VDJ.insert(3, "Pathology", alignment_result_VDJ.pop("Epitope species"))
    alignment_result_VDJ = alignment_result_VDJ[alignment_result_VDJ["Species"] == VDJ_Species]

    alignment_result_McPASTCR_Pathology = pd.DataFrame()
    alignment_result_McPASTCR_Category = pd.DataFrame()

    if contained_Pathology:
        alignment_result_McPASTCR_Pathology = alignment_result_McPASTCR[
            alignment_result_McPASTCR["Pathology"].isin(use_Pathology)]
        alignment_result_VDJ = alignment_result_VDJ[alignment_result_VDJ["Pathology"].isin(use_Pathology)]

    if contained_Category_McPASTCR:
        alignment_result_McPASTCR_Category = alignment_result_McPASTCR[
            alignment_result_McPASTCR["Category"].isin(use_Category)]

    if contained_Pathology or contained_Category_McPASTCR:
        alignment_result_McPASTCR = pd.concat([alignment_result_McPASTCR_Pathology, alignment_result_McPASTCR_Category])
        alignment_result_McPASTCR = alignment_result_McPASTCR.drop_duplicates()

    from appone.constant import PROJECT_FILE
    alignment_savepath = PROJECT_FILE + f"/{projectName}/alignment/"
    if not os.path.exists(alignment_savepath):
        os.makedirs(alignment_savepath)
    alignment_save_VDJ = alignment_savepath + sample + "__" + chain + "__VDJdb.csv"
    alignment_save_McPASTCR = alignment_savepath + sample + "__" + chain + "__McPASTCR.csv"
    alignment_result_VDJ.to_csv(alignment_save_VDJ, index=False)
    alignment_result_McPASTCR.to_csv(alignment_save_McPASTCR, index=False)
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        db = client[projectName]
        col_name = db[projectName + "_" + "alignment"]
        data = {
            "sample":sample,
            "chain":chain,
            "VDJdb":alignment_result_VDJ.to_dict(orient='list'),
            "McPASTCR":alignment_result_McPASTCR.to_dict(orient='list'),
        }
        col_name.insert_one(data)
    except Exception as e:
        print(e)
    finally:
        client.close()
    Epitope_specify_ratio_VDJ = df_pep[df_pep["CDR3(pep)"].isin(alignment_result_VDJ["CDR3(pep)"])]["copy"].sum() / \
                                df_pep["copy"].sum()
    Epitope_specify_ratio_McPASTCR = df_pep[df_pep["CDR3(pep)"].isin(alignment_result_McPASTCR["CDR3(pep)"])][
                                         "copy"].sum() / df_pep["copy"].sum()

    return (sample, chain, Epitope_specify_ratio_VDJ, Epitope_specify_ratio_McPASTCR)


# runtime = parmap.map_async(alignment, pep_paths)
# runtime.wait()
# result = runtime.get()
# result = list(filter(None, result))


# for pep_path in pep_paths:
#     alignment(pep_path)
def get_df_specify_ratio(result: List[Tuple[str, str, float, float]], projectName: str, df_profile: pd.DataFrame, category: List[str]) -> None:
    """
    整理比对结果，生成特异性比例数据框并保存到 CSV 和数据库中。
    """
    print("get_df_specify_ratio...")
    dict_specify_ratio = {"TRA_ratio_VDJdb": {}, "TRA_ratio_McPASTCR": {}, "TRB_ratio_VDJdb": {},
                          "TRB_ratio_McPASTCR": {}}
    for result_item in result:
        sample = result_item[0]
        chain = result_item[1]
        ratio_VDJdb = result_item[2]
        ratio_McPASTCR = result_item[3]
        if chain == "TRA":
            dict_specify_ratio["TRA_ratio_VDJdb"][sample] = ratio_VDJdb
            dict_specify_ratio["TRA_ratio_McPASTCR"][sample] = ratio_McPASTCR
        if chain == "TRB":
            dict_specify_ratio["TRB_ratio_VDJdb"][sample] = ratio_VDJdb
            dict_specify_ratio["TRB_ratio_McPASTCR"][sample] = ratio_McPASTCR

    df_specify_ratio = pd.DataFrame(dict_specify_ratio).reset_index(names="sample")
    list_1 = ["sample"] + category
    df = pd.merge(df_profile[list_1], df_specify_ratio, how="inner", on="sample")  #.to_csv("specify_ratio.csv",
                                                                            #index=False)
    from appone.constant import PROJECT_FILE
    specify_ratio_savepath = PROJECT_FILE + f"/{projectName}/alignment/specify_ratio/"
    if not os.path.exists(specify_ratio_savepath):
        os.makedirs(specify_ratio_savepath)
    df.to_csv(specify_ratio_savepath + "specify_ratio.csv", index=False)
    try:
        client = pymongo.MongoClient(DBURL, maxidletimems=120000)
        db = client[projectName]
        # TO BOXPLOT
        utils.get_boxplot_condition(df, projectName, db, "db_alignment_boxplot")
        col_name = db[projectName + "_" + "specify_ratio"]
        col_name.insert_many(df.to_dict(orient="records"))
    except Exception as e:
        print(e)
    finally:
        client.close()

'''
datapoint  Category = ["group1","group2"]  all_path [[df1,sample,chain],[df2,sample,chain],[df3,sample,chain]]
  VDJ_DB McPASTCR_DB
'''


def start_func(datapoint: pd.DataFrame, Category2: List[str], all_path: List[List[Any]]) -> None:
    """
    启动比对流程：运行比对任务，整理结果，并复制箱线图结果。
    """
    print("start_func")
    # global df_profile;
    # df_profile = datapoint
    # global category;
    # category = Category2
    runtime = parmap.map_async(alignment, all_path)
    runtime.wait()
    result = runtime.get()
    result = list(filter(None, result))
    projectName = all_path[0][5]
    get_df_specify_ratio(result,projectName,datapoint,Category2)
    src_folder = PROJECT_FILE + f"/{projectName}/boxplot/db_alignment_boxplot"
    target_path = PROJECT_FILE + f"/{projectName}/alignment/specify_ratio/boxplot"
    shutil.copytree(src_folder, target_path)  # 复制
    shutil.rmtree(src_folder)
