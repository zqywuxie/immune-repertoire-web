from sonnia.sonnia import SoNNia
from sonnia.sonia import Sonia
from sonnia.plotting import Plotter
from sonnia.processing import Processing
import numpy as np
import pandas as pd
import os
import parmap
df_profille = pd.read_csv("./Profile_All.csv",usecols=["sample","therapy","disease"])

Pgen_mean_dict = {}
for dirname,dirs,filenames in os.walk("./artificial_peps"):
    for filename in filenames:
        chain = filename.split("__")[-1].split(".")[0]
        colname = "Pgen_"+chain
        if colname not in Pgen_mean_dict.keys():
            Pgen_mean_dict[colname] = {}
        if chain == "TRD" or chain == "TRG":
            continue
        sample = filename.split("__")[0]
        args = (chain,sample,os.path.join(dirname,filename))
        Species = "human"
        chain = args[0]
        sample = args[1]
        df = pd.read_csv(args[2],usecols=["CDR3(pep)","V","J"])
        df.drop_duplicates(["CDR3(pep)","V","J"],inplace=True)
        df.columns = ["amino_acid","v_gene","j_gene"]
        model_name = Species+chain
        processor=Processing(pgen_model=model_name)
        filtered=processor.filter_dataframe(df)
        data_seqs=filtered.values.astype(str)
        qm = SoNNia(data_seqs=data_seqs,pgen_model=model_name)
        Q_data,pgen_data,ppost_data=qm.evaluate_seqs(qm.data_seqs)
        df_Pgen = pd.DataFrame(qm.data_seqs,columns=['CDR3(pep)','V',"J"])
        df_Pgen.insert(3,'Pgen',pgen_data)
        df_Pgen.insert(4,'Q',Q_data)
        df_Pgen.insert(5,'Ppost',ppost_data)
        df_Pgen['V'] = chain + df_Pgen["V"].str.upper()
        df_Pgen['J'] = chain + df_Pgen["J"].str.upper()
        mean_pgen = df_Pgen['Pgen'].mean()
        Pgen_mean_dict[colname][sample] = mean_pgen
        Pgendf_savepath = "./Pgen/"+sample+"/"
        if not os.path.exists(Pgendf_savepath):
            os.makedirs(Pgendf_savepath)
        df_Pgen.to_csv(Pgendf_savepath+chain+".csv",index=False)

Pgen_all = pd.DataFrame(Pgen_mean_dict)
Pgen_all.reset_index(names="sample",inplace=True)
pd.merge(df_profille,Pgen_all,on="sample").to_csv("Pgen_mean.csv",index=False)