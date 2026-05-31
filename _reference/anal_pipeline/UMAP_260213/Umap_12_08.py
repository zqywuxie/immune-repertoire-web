import os
from copy import deepcopy
from itertools import combinations

import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu
from sklearn.preprocessing import StandardScaler
import umap


"""
file_dir can be a filename or a dirname
"""
file_dir = "Datapoint"

"""
if filename_or_file = 1, input is an dirname
if filename_or_file = 0, input will be an filename
"""
filename_or_file = 1

"""
the threshold of p_value, if smaller than the thresh,the data can be in calculating and plot the boxes.
"""
threshold_pvalue = 0.05

"""
Find the combination in class, the data_split_point_begin is the beginning postion 
but it not contain the number positon, eg. if data_split_point_begin = "Group1", data_split_point = "Group2",
"""
data_split_point_begin = "therapy"
data_split_point_over = "disease"

"""
Which decide the parameters count into calculate, including the param name
"""

param_begin = "TRA_percent_reads_all"
param_over = "IGHM_IGHD_VDJnuc_SHM1"


"""
Remove the sepcified type in dataframe
"""
remove_list = [0]

"""
Specify the boxplot bar type as multiple or pair
if pair_or_mutiple = 1, plot the mutiple index umap
if pair_or_mutiple = 0, just the pair index umap
"""
pair_or_mutiple = 1

"""
min_distance which define the min distance of the two point
n_neighbors defines the cluster number of point
"""
umap_n_neighbors = 6
umap_min_dist = 0.01


def get_filesdir(file_dir):
    """
    Get the filesdir
    @return: a list of path or paths
    """
    if filename_or_file == 0:
        return [file_dir]
    if filename_or_file == 1:
        path_list = []
        for root, dirnames, filenames in os.walk(file_dir):
            for filename in filenames:
                path_list.append(os.path.join(root, filename))
        return path_list


def get_removed_subdf(dataframe):
    """
    Remove the specified type in dataframe
    @return: the Pandas Dataframe of specified removed dataframe
    """
    return dataframe


def get_class_dict(dataframe):
    """
    @return: class_dict structure:{"colname":[type1,type2]}
    The previous csv Global Method of getting the class_dict, the dict structure:{"colname":[type1,type2]}
    example:{'lung_infection':['Neg', 'Positive'],…}
    """
    begin = dataframe.columns.tolist().index(data_split_point_begin)
    over = dataframe.columns.tolist().index(data_split_point_over) + 1
    class_dict = {}
    for col_name in dataframe.columns[begin:over]:
        col_type_list = []
        for arg in dataframe[col_name]:
            if arg not in col_type_list:
                col_type_list.append(arg)
        for remove_item in remove_list:
            if remove_item in col_type_list:
                col_type_list.remove(remove_item)
        class_dict[col_name] = col_type_list
    return class_dict


def pvalue_list_all(df):
    """
    Get the previous csvs all Pvalue
    @return: The dict, which structure below
    {"colname":[(type1,type2,argument,Pvalue),(type1,type2,argument,Pvalue)]} such as
    {"lung_infection":[("Neg","Positive","Reads_UMI",0.123),…]}
    """
    global class_dict
    param_begin_position = df.columns.tolist().index(param_begin)
    param_over_position = df.columns.tolist().index(param_over) + 1
    class_dict = get_class_dict(df)
    p_value_all = {}
    for colname, itemlist in class_dict.items():
        p_value_all[colname] = []
        combination_list = list(combinations(itemlist, 2))
        for cb in combination_list:
            for param_col in df.columns[param_begin_position:param_over_position]:
                try:
                    pvalue = mannwhitneyu(
                        df[df[colname] == cb[0]][param_col],
                        df[df[colname] == cb[1]][param_col],
                        alternative='two-sided'
                    ).pvalue
                    p_value_all[colname].append((cb[0], cb[1], param_col, pvalue))
                except Exception:
                    continue
    return p_value_all


def find_cateToparam(p_value_all):
    pair_dict = {}
    all_dict = {}
    all_dict_Pvalue = {}
    for category, pvalue_tuples_list in p_value_all.items():
        pair_dict[category] = {}
        all_dict[category] = {}
        all_dict_Pvalue[category] = {}

        cb_list = []
        if len(class_dict[category]) > 3:
            for i in range(len(class_dict[category]) + 1)[3:]:
                cb_list = cb_list + list(combinations(class_dict[category], i))
        else:
            cb_list = list(combinations(class_dict[category], 2))

        for pvalue_tuple in pvalue_tuples_list:
            pair_tuple = (pvalue_tuple[0], pvalue_tuple[1])
            if pvalue_tuple[3] <= threshold_pvalue:
                if pair_tuple not in pair_dict[category].keys():
                    pair_dict[category][pair_tuple] = {pvalue_tuple[2]: pvalue_tuple[3]}
                else:
                    pair_dict[category][pair_tuple][pvalue_tuple[2]] = pvalue_tuple[3]

                for cb in cb_list:
                    if pvalue_tuple[0] in cb and pvalue_tuple[1] in cb:
                        if cb not in all_dict[category].keys():
                            all_dict[category][cb] = [pvalue_tuple[2]]
                            all_dict_Pvalue[category][cb] = [pvalue_tuple]
                            continue
                        if pvalue_tuple[2] not in all_dict[category][cb]:
                            all_dict[category][cb].append(pvalue_tuple[2])
                        all_dict_Pvalue[category][cb].append(pvalue_tuple)

        temporary_dict = deepcopy(all_dict_Pvalue[category])
        for cb, tuple_params_list in temporary_dict.items():
            params = []
            for pvalue_tuple in tuple_params_list:
                if pvalue_tuple[0] not in params:
                    params.append(pvalue_tuple[0])
                if pvalue_tuple[1] not in params:
                    params.append(pvalue_tuple[1])
            if len(params) != len(cb):
                del (all_dict_Pvalue[category][cb])
                del (all_dict[category][cb])
        del temporary_dict

        if len(pair_dict[category].keys()) == 0:
            del pair_dict[category]
        if len(all_dict[category].keys()) == 0:
            del all_dict[category]
        if len(all_dict_Pvalue[category].keys()) == 0:
            del all_dict_Pvalue[category]
    return pair_dict, all_dict, all_dict_Pvalue


def replacedot(name):
    name = name.replace(",", "")
    name = name.replace(" ", " vs. ")
    name = name.replace("'", "")
    return name


def draw_umap_all(dataframe, all_dict, all_dict_Pvalue, file_name, root_path):
    """
    For each (category, group_of_types, selected_params), compute UMAP embedding and:
      1) save figure png
      2) save csv containing per-point metadata + umap_x/umap_y
      3) save a small meta txt for reproducibility
    """
    for category, map_dict in all_dict.items():
        MinCategory_Num = umap_n_neighbors
        types = dataframe[category].unique().tolist()
        for type_name in types:
            num = dataframe[dataframe[category] == type_name].shape[0]
            if num < MinCategory_Num:
                MinCategory_Num = num

        umap_n_neighbors_local = umap_n_neighbors
        if MinCategory_Num < umap_n_neighbors:
            umap_n_neighbors_local = MinCategory_Num

        for type_tuple, params in map_dict.items():
            type_list = list(type_tuple)

            # build subset df
            use_df = pd.DataFrame(columns=dataframe.columns)
            for ctype in type_list:
                use_df = use_df._append(dataframe[dataframe[category] == ctype])

            # map category -> int for coloring
            map_str = "use_df." + category + ".map"
            map_dic = {iostype: i for iostype, i in zip(type_list, range(len(type_list)))}
            color_class_list = [[x] for x in eval(map_str + '(' + str(map_dic) + ')')]

            # UMAP
            bio_data = use_df[params].values
            scaled_bio_data = StandardScaler().fit_transform(bio_data)
            reducer = umap.UMAP(
                n_neighbors=umap_n_neighbors_local,
                min_dist=umap_min_dist,
                n_epochs=50,
                random_state=42
            )
            embedding = reducer.fit_transform(scaled_bio_data)

            # ---------- plot ----------
            scatter = plt.scatter(
                embedding[:, 0],
                embedding[:, 1],
                c=color_class_list
            )
            plt.legend(handles=scatter.legend_elements()[0], labels=type_list, title=category)
            plt.gca().set_aspect('equal', 'datalim')

            # title & paths
            name = str(type_tuple).replace("(", "").replace(")", "")
            name = replacedot(name)
            plt.title('UMAP of ' + name + " in " + category, fontsize=12)

            figure_path = os.path.join(root_path, file_name, category)
            if not os.path.exists(figure_path):
                os.makedirs(figure_path)
            plt.savefig(os.path.join(figure_path, name + ".pdf"), bbox_inches='tight', dpi=300)
            plt.clf()

            # ---------- save point info ----------
            labels_int = [int(x[0]) for x in color_class_list]
            int2type = {i: t for i, t in enumerate(type_list)}
            types_str = [int2type[i] for i in labels_int]

            # Keep: category + params + UMAP coords + labels + group/meta
            umap_points = use_df[[category] + list(params)].copy()
            umap_points["umap_x"] = embedding[:, 0]
            umap_points["umap_y"] = embedding[:, 1]
            umap_points["umap_label"] = labels_int
            umap_points["umap_type"] = types_str

            # helpful provenance columns
            umap_points["umap_params"] = "|".join(list(params))
            umap_points["umap_category"] = category
            umap_points["umap_group"] = name
            umap_points["umap_n_neighbors"] = umap_n_neighbors_local
            umap_points["umap_min_dist"] = umap_min_dist
            umap_points["umap_random_state"] = 40
            umap_points["umap_n_epochs"] = 50

            csv_files = os.path.join(root_path, "csv_file", file_name, category)
            if not os.path.exists(csv_files):
                os.makedirs(csv_files)

            umap_points.to_csv(os.path.join(csv_files, name + "_umap_points.csv"))

            # ---------- save meta ----------
            meta_path = os.path.join(csv_files, name + "_umap_meta.txt")
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write(f"category={category}\n")
                f.write(f"group={name}\n")
                f.write(f"types={type_list}\n")
                f.write(f"params={list(params)}\n")
                f.write(f"n_neighbors={umap_n_neighbors_local}\n")
                f.write(f"min_dist={umap_min_dist}\n")
                f.write("random_state=40\n")
                f.write("n_epochs=50\n")


def draw(data_path):
    filepath, filename = os.path.split(data_path)
    stem, suffix = os.path.splitext(filename)

    df = pd.read_csv(data_path, index_col=0)
    df.fillna(0, inplace=True)

    p_value_all = pvalue_list_all(df)
    pair_dict, all_dict, all_dict_Pvalue = find_cateToparam(p_value_all)

    draw_umap_all(
        dataframe=df,
        all_dict=all_dict,
        all_dict_Pvalue=all_dict_Pvalue,
        file_name=stem,
        root_path="umap_all"
    )


# -----------------------------
# main
# -----------------------------
for data_path in get_filesdir(file_dir):
    draw(data_path)
