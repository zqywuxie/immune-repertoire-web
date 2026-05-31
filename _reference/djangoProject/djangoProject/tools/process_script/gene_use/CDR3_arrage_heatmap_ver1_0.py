import os, sys

os.chdir(sys.path[0])
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from appone.constant import PROJECT_FILE
import parmap
import warnings
from typing import List, Any

warnings.filterwarnings("ignore", category=FutureWarning)


def get_csv_path(projectName: str) -> List[str]:
    """
    获取指定项目下所有排列后的 CDR3 共享数据的 CSV 文件路径。
    """
    csv_files = []
    path = PROJECT_FILE + f"/{projectName}/cdr3_share/arrage_pep/"
    for dirname, dirs, filenames in os.walk(path):
        for filename in filenames:
            csv_files.append(os.path.join(dirname, filename))
    return csv_files


def plot_heatmap(data_list: List[Any]) -> None:
    """
    根据给定的项目名和 CSV 路径，绘制并保存 CDR3 共享热图。
    """
    csv_path = data_list[1]
    group = os.path.basename(os.path.dirname(csv_path))
    projectName = data_list[0]
    # for csv_path in csv_files:
    data_end = 0
    df = pd.read_csv(csv_path)
    if df.shape[0] == 1:
        return 0  # continue
    for i in range(len(df.iloc[0])):
        if df.iloc[0][df.columns[i]] == " ":
            data_end = i
            break
    cate = df.iloc[0].unique()[1:-1].tolist()
    flag_count = 0
    cate_all = eval(df.category.unique()[-1])
    cate_all = list(map(lambda x: x.split("__"), cate_all))
    cate_all = [i[0] for i in cate_all]
    if cate_all == cate:
        end_row = df[df.category == df.category.unique()[-1]].index[0]
    else:
        end_row = df.shape[0]
    df_s = df[df.columns[1:data_end]].iloc[1:]
    # df_s = df[df.columns[1:data_end]].iloc[1:end_row]
    df_s = df_s.apply(pd.to_numeric)
    # df_s = df_s.div(df_s.sum(axis=1), axis=0)
    df_s[df_s > 1] = 1
    plt.figure(figsize=(20, 8))
    try:
        sns.set_palette("pastel")
        ax = sns.heatmap(df_s, square=False, cmap="BuGn", cbar_kws={"aspect": 100, "pad": 0.0005}, cbar=False)
        # cbar = ax.collections[0].colorbar
        ax.get_yaxis().set_visible(False)
        # cbar.ax.tick_params(labelsize=10)
        parameters = {"xtick.labelsize": 10}
        plt.rcParams.update(parameters)
        save_path = PROJECT_FILE + f"/{projectName}/cdr3_share/CDR3_arrage_heatmap/{group}"  # "./CDR3_arrage_heatmap"
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        ax.figure.savefig(os.path.join(save_path, os.path.split(csv_path)[1][:-4]), bbox_inches='tight', dpi=600)
    except Exception as e:
        print(f"CDR3_heatmap have error:{e}")
    plt.cla()


def start_func(projectName: str) -> None:
    """
    启动 CDR3 共享热图绘制流程。
    """
    # with open("./4_28.txt", "w") as f:
    #     f.write(f"{projectName}的CDR3_arrage_heatmap开始计算。")

    csv_files = get_csv_path(projectName)
    datas = []
    for csv_path in csv_files:
        datas.append([projectName, csv_path])

    for data in datas:
        # print(data)
        plot_heatmap(data)
    # runtime = parmap.map_async(plot_heatmap, datas)
    # runtime.wait()
    # result = runtime.get()
