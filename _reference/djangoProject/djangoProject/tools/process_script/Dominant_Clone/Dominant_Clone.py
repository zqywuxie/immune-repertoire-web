import pandas as pd
import os
import parmap
from  djangoProject.tools.process_func import utils
from typing import List, Tuple, Any, Dict
"[[db,sample,chain,top_x],[db,sample,chain,top_x]]"
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

def read_csv(args: List[Any]) -> Tuple[pd.DataFrame, str, str]:
    """
    读取单个样本数据并提取前 top_x 个克隆。
    """
    # save_dir = "./Dominant_Clone/"
    df = args[0]
    sample = args[1]
    chain = args[2]
    top_x = args[3]

    # save_path = save_dir + sample + "/"
    # try:
    #     if not os.path.exists(save_path):
    #         os.makedirs(save_path)
    # except:
    #     None
    df = df[["CDR3(pep)", "copy"]]
    # db = pd.read_csv(path,usecols=["CDR3(pep)","copy"])
    if df.shape[0] < 10:
        return (df, sample, chain)
    df = df.groupby("CDR3(pep)").sum().sort_values("copy", ascending=False).iloc[:top_x].reset_index()

    # db.to_csv(save_path + chain + ".csv", index=False)
    return (df, sample, chain)


"[[db,sample,chain,top_x],[db,sample,chain,top_x]]"


def function(paths: List[List[Any]], datapoint: pd.DataFrame, category: List[str], projectName: str) -> None:
    """
    分析优势克隆：计算各样本各链的优势克隆矩阵，并根据分类信息保存。
    """
    top_x = 10
    for path in paths:
        path.append(top_x)
    runtime = parmap.map_async(read_csv, paths, pm_processes=16)
    runtime.wait()
    result = runtime.get()

    Dominant_Clone_Dict = {}
    for (df, sample, chain) in result:
        if sample not in Dominant_Clone_Dict.keys():
            Dominant_Clone_Dict[sample] = {chain: df}
        else:
            Dominant_Clone_Dict[sample][chain] = df
    chain2Dominant_matrix = {}

    for chain in ["TRA", "TRB", "TRD", "TRG", "IGH", "IGK", "IGL"]:
        df_Dominant_matrix = pd.DataFrame(columns=["CDR3(pep)"])

        for sample, chain2df in Dominant_Clone_Dict.items():
            if chain not in chain2df.keys():
                continue
            df = chain2df[chain].copy()
            df[sample] = df.pop("copy")
            df_Dominant_matrix = pd.merge(df_Dominant_matrix, df, on="CDR3(pep)", how="outer")
        from appone.constant import PROJECT_FILE
        save_path = PROJECT_FILE + f"/{projectName}/cdr3_clone/Dominant_Clone/Dominant_Matrix/"
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        if not df_Dominant_matrix.empty:
            df_Dominant_matrix.to_csv(save_path + chain + ".csv", index=False)
            data = {
                "projectName":projectName,
                "chain": chain,
                "df":df_Dominant_matrix.to_dict(orient="list")
            }
            utils.data_save_to_db(data, "Dominant_Matrix",projectName)
            chain2Dominant_matrix[chain] = df_Dominant_matrix
    # add cate
    profile = datapoint
    use_categorys = category
    from appone.constant import PROJECT_FILE
    root_path =PROJECT_FILE+ f"/{projectName}/cdr3_clone/Dominant_Clone/Dominant_Matrix2Categroy/"
    for use_category in use_categorys:
        samples = profile[profile[use_category].isin(profile[use_category].dropna().unique().tolist())][
            "sample"].tolist()
        save_path = root_path + use_category + "/"
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        for chain, matrix in chain2Dominant_matrix.items():
            use_matrix = matrix[["CDR3(pep)"] + samples].copy()
            use_matrix.index = use_matrix.pop("CDR3(pep)")
            use_matrix.index.name = "CDR3(pep)"
            use_matrix.fillna(0, inplace=True)
            use_matrix = use_matrix.loc[~(use_matrix == 0).all(axis=1)]
            use_matrix = use_matrix.T
            use_matrix.insert(loc=0, column="sample", value=use_matrix.index)
            use_matrix = pd.merge(profile[["sample", use_category]], use_matrix)
            data = {
                "projectName":projectName,
                "group": use_category,
                "chain": chain,
                "df":use_matrix.to_dict(orient="list")
            }
            utils.data_save_to_db(data,"Dominant_Matrix2Categroy",projectName)
            use_matrix.to_csv(save_path + chain + ".csv", index=False)


def start_func(projectName: str, paths: List[List[Any]], datapoint: pd.DataFrame, category: List[str]) -> None:
    """
    启动优势克隆分析。
    """
    function(paths, datapoint,category,projectName)
