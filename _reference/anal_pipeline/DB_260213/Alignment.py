import pandas as pd
import os
import parmap

profile = "./Profile_All.csv"
categorys = ["therapy","disease"]
df_profile = pd.read_csv(profile)
contained_Pathology = False
use_Pathology = ["Diabetes Type 1"]

pep_paths = []
for dirname,dirs,filenames in os.walk("./artificial_peps"):
    for filename in filenames:
        pep_paths.append(os.path.join(dirname,filename))


def alignment(path):
    VDJ_DB = pd.read_csv("./DB/vdjdb.csv",low_memory=False)
    VDJ_DB["PubMed.ID"] = VDJ_DB["Reference"].astype(str)
    McPASTCR_DB = pd.read_csv("./DB/McPAS-TCR.csv",low_memory=False)
    McPASTCR_DB["PubMed.ID"] = McPASTCR_DB["PubMed.ID"].astype(str)
    df_pep = pd.read_csv(path,low_memory=False)
    sample_pep = path.split("/")[-1]
    sample = sample_pep.split("__")[0]
    chain = sample_pep.split("__")[-1].split(".csv")[0]
    
    if chain not in ["TRA","TRB"]:
        return
    
    if chain == "TRA":
        alignment_result_McPASTCR = McPASTCR_DB[McPASTCR_DB["CDR3.alpha.aa"].isin(df_pep["CDR3(pep)"].tolist())][["CDR3.alpha.aa","Species","Epitope.peptide","Pathology","PubMed.ID"]]
        alignment_result_McPASTCR.insert(0,"CDR3(pep)",alignment_result_McPASTCR.pop("CDR3.alpha.aa"))
        alignment_result_McPASTCR = alignment_result_McPASTCR[alignment_result_McPASTCR["Species"]=="Human"]
    else:
        alignment_result_McPASTCR = McPASTCR_DB[McPASTCR_DB["CDR3.beta.aa"].isin(df_pep["CDR3(pep)"].tolist())][["CDR3.beta.aa","Species","Epitope.peptide","Pathology","PubMed.ID"]]
        alignment_result_McPASTCR.insert(0,"CDR3(pep)",alignment_result_McPASTCR.pop("CDR3.beta.aa"))
        alignment_result_McPASTCR = alignment_result_McPASTCR[alignment_result_McPASTCR["Species"]=="Human"]


    alignment_result_VDJ = VDJ_DB[VDJ_DB["CDR3"].isin(df_pep["CDR3(pep)"].tolist())][["CDR3","Species","Epitope","Epitope species","Reference"]]
    alignment_result_VDJ.insert(0,"CDR3(pep)",alignment_result_VDJ.pop("CDR3"))
    alignment_result_VDJ.insert(2,"Epitope.peptide",alignment_result_VDJ.pop("Epitope"))
    alignment_result_VDJ.insert(3,"Pathology",alignment_result_VDJ.pop("Epitope species"))
    alignment_result_VDJ = alignment_result_VDJ[alignment_result_VDJ["Species"]=="HomoSapiens"]

    if contained_Pathology:
        alignment_result_McPASTCR = alignment_result_McPASTCR[alignment_result_McPASTCR["Pathology"].isin(use_Pathology)] 
        alignment_result_VDJ = alignment_result_VDJ[alignment_result_VDJ["Pathology"].isin(use_Pathology)]

    alignment_savepath = "./alignment/"
    if not os.path.exists(alignment_savepath):
        os.makedirs(alignment_savepath)
    alignment_save_VDJ = alignment_savepath+sample+"__"+chain+"__VDJdb.csv"
    alignment_save_McPASTCR = alignment_savepath+sample+"__"+chain+"__McPASTCR.csv"
    
    alignment_result_VDJ.to_csv(alignment_save_VDJ,index=False)
    alignment_result_McPASTCR.to_csv(alignment_save_McPASTCR,index=False)

    Epitope_specify_ratio_VDJ = df_pep[df_pep["CDR3(pep)"].isin(alignment_result_VDJ["CDR3(pep)"])]["copy"].sum()/df_pep["copy"].sum()
    Epitope_specify_ratio_McPASTCR = df_pep[df_pep["CDR3(pep)"].isin(alignment_result_McPASTCR["CDR3(pep)"])]["copy"].sum()/df_pep["copy"].sum()

    return (sample,chain,Epitope_specify_ratio_VDJ,Epitope_specify_ratio_McPASTCR)


runtime = parmap.map_async(alignment,pep_paths)
runtime.wait()
result = runtime.get()
result = list(filter(None, result)) 

dict_specify_ratio = {"TRA_ratio_VDJdb":{},"TRA_ratio_McPASTCR":{},"TRB_ratio_VDJdb":{},"TRB_ratio_McPASTCR":{}}
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
pd.merge(df_profile[["sample"]+categorys],df_specify_ratio,how="inner",on="sample").to_csv("specify_ratio.csv",index=False)