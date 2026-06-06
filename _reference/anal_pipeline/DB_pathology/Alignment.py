import os
import re
from pathlib import Path

import pandas as pd
import parmap

# Sample column setting.
# Modify SAMPLE_COLUMN when the sample field name differs across files.
SAMPLE_COLUMN = "Sample"

# When enabled:
# 1. alignment results are split into per-pathology folders under alignment/
# 2. specify_ratio outputs include the overall summary and one summary per pathology
CLASSIFY_BY_PATHOLOGY = True

# Optional pathology filter for classification mode.
# Leave empty to export all pathology categories found in the alignment result.
use_Pathology = []

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

profile = "/data/scAnalyis/260416/Data/Datapoint/profile_complete.csv"
df_profile = pd.read_csv(profile)
if SAMPLE_COLUMN not in df_profile.columns:
    raise KeyError(
        f"Column '{SAMPLE_COLUMN}' was not found in {profile}. "
        "Please update SAMPLE_COLUMN at the top of Alignment.py."
    )
categorys = ["group_type", "timepoint"]

pep_root_candidates = [
    Path("/data/scAnalyis/260416/Data/pep_data"),
]

pep_root = next((path for path in pep_root_candidates if path.exists()), None)
if pep_root is None:
    raise FileNotFoundError(
        "No pep data directory found. Checked: "
        + ", ".join(str(path) for path in pep_root_candidates)
    )

pep_paths = []
for dirname, dirs, filenames in os.walk(pep_root):
    for filename in filenames:
        if filename.endswith(".csv") or filename.endswith(".csv.gz"):
            pep_paths.append(os.path.join(dirname, filename))
pep_paths.sort()


# 得到pathology分类的文件夹名称
def sanitize_name(name):
    sanitized = re.sub(r'[\\/:*?"<>|]+', "_", str(name)).strip()
    return sanitized or "Unknown"


def empty_ratio_dict():
    return {
        "TRA_ratio_VDJdb": {},
        "TRA_ratio_McPASTCR": {},
        "TRB_ratio_VDJdb": {},
        "TRB_ratio_McPASTCR": {},
    }


# 将样本的TRA/TRB比例添加到对应的字典中
def add_chain_ratios(ratio_dict, sample, chain, ratio_vdj, ratio_mcpastcr):
    if chain == "TRA":
        ratio_dict["TRA_ratio_VDJdb"][sample] = ratio_vdj
        ratio_dict["TRA_ratio_McPASTCR"][sample] = ratio_mcpastcr
    if chain == "TRB":
        ratio_dict["TRB_ratio_VDJdb"][sample] = ratio_vdj
        ratio_dict["TRB_ratio_McPASTCR"][sample] = ratio_mcpastcr


def build_specify_ratio_df(ratio_dict):
    valid_categorys = [c for c in categorys if c in df_profile.columns]
    df_specify_ratio = pd.DataFrame(ratio_dict).reset_index()
    df_specify_ratio = df_specify_ratio.rename(columns={"index": SAMPLE_COLUMN})
    return pd.merge(
        df_profile[[SAMPLE_COLUMN] + valid_categorys],
        df_specify_ratio,
        how="inner",
        on=SAMPLE_COLUMN,
    )


def compute_ratio(df_pep, matched_cdr3_values):
    total_copy = df_pep["copy"].sum()
    if total_copy == 0:
        return 0
    return (
        df_pep[df_pep["CDR3(pep)"].isin(matched_cdr3_values)]["copy"].sum() / total_copy
    )


def collect_pathologies(alignment_result_vdj, alignment_result_mcpastcr):
    if use_Pathology:
        return list(use_Pathology)
    return sorted(
        set(alignment_result_vdj["Pathology"].fillna("Unknown").astype(str).tolist())
        | set(
            alignment_result_mcpastcr["Pathology"]
            .fillna("Unknown")
            .astype(str)
            .tolist()
        )
    )


def save_alignment_results(
    alignment_result_vdj, alignment_result_mcpastcr, sample, chain
):
    alignment_savepath = SCRIPT_DIR / "alignment"
    alignment_savepath.mkdir(exist_ok=True)

    if not CLASSIFY_BY_PATHOLOGY:
        alignment_result_vdj.to_csv(
            alignment_savepath / f"{sample}__{chain}__VDJdb.csv",
            index=False,
        )
        alignment_result_mcpastcr.to_csv(
            alignment_savepath / f"{sample}__{chain}__McPASTCR.csv",
            index=False,
        )
        return

    for pathology in collect_pathologies(
        alignment_result_vdj, alignment_result_mcpastcr
    ):
        pathology_savepath = alignment_savepath / sanitize_name(pathology)
        pathology_savepath.mkdir(exist_ok=True)

        alignment_result_vdj[
            alignment_result_vdj["Pathology"].fillna("Unknown").astype(str)
            == str(pathology)
        ].to_csv(
            pathology_savepath / f"{sample}__{chain}__VDJdb.csv",
            index=False,
        )
        alignment_result_mcpastcr[
            alignment_result_mcpastcr["Pathology"].fillna("Unknown").astype(str)
            == str(pathology)
        ].to_csv(
            pathology_savepath / f"{sample}__{chain}__McPASTCR.csv",
            index=False,
        )


def write_specify_ratio_outputs(overall_ratio_dict, pathology_ratio_dict):
    specify_ratio_dir = SCRIPT_DIR / "specify_ratio"
    specify_ratio_dir.mkdir(exist_ok=True)

    build_specify_ratio_df(overall_ratio_dict).to_csv(
        specify_ratio_dir / "specify_ratio.csv",
        index=False,
    )

    if not CLASSIFY_BY_PATHOLOGY:
        return

    for pathology, ratio_dict in sorted(pathology_ratio_dict.items()):
        build_specify_ratio_df(ratio_dict).to_csv(
            specify_ratio_dir / f"specify_ratio__{sanitize_name(pathology)}.csv",
            index=False,
        )


def alignment(path):
    VDJ_DB = pd.read_csv(SCRIPT_DIR / "DB" / "vdjdb.csv", low_memory=False)
    VDJ_DB["PubMed.ID"] = VDJ_DB["Reference"].astype(str)
    McPASTCR_DB = pd.read_csv(SCRIPT_DIR / "DB" / "McPAS-TCR.csv", low_memory=False)
    McPASTCR_DB["PubMed.ID"] = McPASTCR_DB["PubMed.ID"].astype(str)
    df_pep = pd.read_csv(path, low_memory=False)
    df_pep["CDR3_match"] = df_pep["CDR3(pep)"].apply(
        lambda x: (
            x
            if isinstance(x, str) and x.startswith("C")
            else ("C" + x if isinstance(x, str) else x)
        )
    )

    cdr3_lookup = df_pep[["CDR3(pep)", "CDR3_match"]].drop_duplicates()
    pep_copy = df_pep.groupby("CDR3(pep)", as_index=False)["copy"].sum()

    sample_pep = path.split("/")[-1]
    if sample_pep.endswith(".csv.gz"):
        sample_pep = sample_pep[:-3]  # strip .gz → .csv
    name = sample_pep.rsplit(".", 1)[0]
    # Parse sample and chain from filename: {sample}__{chain}.csv or {sample}_{chain}.csv
    # Chains: TRA, TRB, TRD, TRG (TCR); IGH, IGK, IGL (BCR)
    ALL_CHAINS = r"TRA|TRB|TRD|TRG|IGH|IGK|IGL"
    match = re.match(rf"^(.+)__({ALL_CHAINS})$", name)
    if not match:
        match = re.match(rf"^(.+)_({ALL_CHAINS})$", name)
    sample, chain = match.groups() if match else (name, "")
    print(f"Processing sample: {sample}, chain: {chain}")
    if chain not in ["TRA", "TRB"]:
        return None

    if chain == "TRA":
        alignment_result_mcpastcr = McPASTCR_DB[
            McPASTCR_DB["CDR3.alpha.aa"].isin(df_pep["CDR3_match"].dropna().tolist())
        ][["CDR3.alpha.aa", "Species", "Epitope.peptide", "Pathology", "PubMed.ID"]]
        alignment_result_mcpastcr = alignment_result_mcpastcr.rename(
            columns={"CDR3.alpha.aa": "CDR3_match"}
        )
        alignment_result_mcpastcr = alignment_result_mcpastcr.merge(
            cdr3_lookup, on="CDR3_match", how="left"
        ).drop(columns=["CDR3_match"])
        alignment_result_mcpastcr = alignment_result_mcpastcr[
            alignment_result_mcpastcr["Species"] == "Human"
        ]
    else:
        alignment_result_mcpastcr = McPASTCR_DB[
            McPASTCR_DB["CDR3.beta.aa"].isin(df_pep["CDR3_match"].dropna().tolist())
        ][["CDR3.beta.aa", "Species", "Epitope.peptide", "Pathology", "PubMed.ID"]]
        alignment_result_mcpastcr = alignment_result_mcpastcr.rename(
            columns={"CDR3.beta.aa": "CDR3_match"}
        )
        alignment_result_mcpastcr = alignment_result_mcpastcr.merge(
            cdr3_lookup, on="CDR3_match", how="left"
        ).drop(columns=["CDR3_match"])
        alignment_result_mcpastcr = alignment_result_mcpastcr[
            alignment_result_mcpastcr["Species"] == "Human"
        ]

    alignment_result_vdj = VDJ_DB[
        VDJ_DB["CDR3"].isin(df_pep["CDR3_match"].dropna().tolist())
    ][["CDR3", "Species", "Epitope", "Epitope species", "Reference"]]
    alignment_result_vdj = alignment_result_vdj.rename(
        columns={
            "CDR3": "CDR3_match",
            "Epitope": "Epitope.peptide",
            "Epitope species": "Pathology",
        }
    )
    alignment_result_vdj = alignment_result_vdj.merge(
        cdr3_lookup, on="CDR3_match", how="left"
    ).drop(columns=["CDR3_match"])
    alignment_result_vdj = alignment_result_vdj[
        ["CDR3(pep)", "Species", "Epitope.peptide", "Pathology", "Reference"]
    ]
    alignment_result_vdj = alignment_result_vdj[
        alignment_result_vdj["Species"] == "HomoSapiens"
    ]

    alignment_result_mcpastcr = alignment_result_mcpastcr.merge(
        pep_copy,
        on="CDR3(pep)",
        how="left",
    )
    alignment_result_vdj = alignment_result_vdj.merge(
        pep_copy,
        on="CDR3(pep)",
        how="left",
    )

    save_alignment_results(
        alignment_result_vdj, alignment_result_mcpastcr, sample, chain
    )

    overall_ratio_vdj = compute_ratio(df_pep, alignment_result_vdj["CDR3(pep)"])
    overall_ratio_mcpastcr = compute_ratio(
        df_pep, alignment_result_mcpastcr["CDR3(pep)"]
    )

    pathology_ratios = {}
    if CLASSIFY_BY_PATHOLOGY:
        for pathology in collect_pathologies(
            alignment_result_vdj, alignment_result_mcpastcr
        ):

            pathology_vdj = alignment_result_vdj[
                alignment_result_vdj["Pathology"].fillna("Unknown").astype(str)
                == str(pathology)
            ]
            pathology_mcpastcr = alignment_result_mcpastcr[
                alignment_result_mcpastcr["Pathology"].fillna("Unknown").astype(str)
                == str(pathology)
            ]
            pathology_ratios[pathology] = {
                "VDJdb": compute_ratio(df_pep, pathology_vdj["CDR3(pep)"]),
                "McPASTCR": compute_ratio(df_pep, pathology_mcpastcr["CDR3(pep)"]),
            }

    return {
        "sample": sample,
        "chain": chain,
        "overall_vdj": overall_ratio_vdj,
        "overall_mcpastcr": overall_ratio_mcpastcr,
        "pathology_ratios": pathology_ratios,
    }


runtime = parmap.map_async(alignment, pep_paths)
runtime.wait()
result = runtime.get()
result = list(filter(None, result))

overall_ratio_dict = empty_ratio_dict()
pathology_ratio_dict = {}
all_pathologies = []
if CLASSIFY_BY_PATHOLOGY:
    if use_Pathology:
        all_pathologies = list(use_Pathology)
    else:
        all_pathologies = sorted(
            {
                pathology
                for result_item in result
                for pathology in result_item["pathology_ratios"].keys()
            }
        )

for result_item in result:
    sample = result_item["sample"]
    chain = result_item["chain"]
    add_chain_ratios(
        overall_ratio_dict,
        sample,
        chain,
        result_item["overall_vdj"],
        result_item["overall_mcpastcr"],
    )

    for pathology in all_pathologies:
        if pathology not in pathology_ratio_dict:
            pathology_ratio_dict[pathology] = empty_ratio_dict()
        ratio_items = result_item["pathology_ratios"].get(
            pathology,
            {"VDJdb": 0, "McPASTCR": 0},
        )
        add_chain_ratios(
            pathology_ratio_dict[pathology],
            sample,
            chain,
            ratio_items["VDJdb"],
            ratio_items["McPASTCR"],
        )

write_specify_ratio_outputs(overall_ratio_dict, pathology_ratio_dict)
