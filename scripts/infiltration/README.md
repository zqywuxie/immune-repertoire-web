# 免疫浸润脚本来源与平台适配

来源：用户原始目录 `E:/Desktop/project/immune_pipeline/pipeline`。
仅纳入 `07.immuneInfiltration/02.plot_deconv_composition.R`、`03.plot_deconv_group_comparison.R`、`plot_deconv_helpers.R` 和 `common/configuration/config.R`，不包含业务数据。

平台适配：编号按文字读取以保留前导零；纵轴使用中文；替换一处青色配色。执行参数使用 150 dpi、关闭逐细胞拆图，输出组成总图、比较总图和统计表。统计定义沿用原始脚本：全局最小值平移加 1e-6 后按行归一化；原始分数双侧 Wilcoxon（exact=FALSE），全部细胞/组对统一 BH 校正。箱线图星号基于原始 p 值，校正结果见 q_value 列。

入口为 `flask_app/services/infiltration_service.py`，输入必须来自当前项目选定数据集；不从文件名推断分组或相对/绝对模式。原始参考目录无需挂载到服务器，所需脚本随应用镜像发布。

部署沿用根目录 `.env` 和 `deploy.sh`。完整分析镜像需要 data.table、ggplot2、patchwork、jsonlite，构建阶段会检查；本轮验证的既有运行环境镜像已包含这些包，无需因本模块重新安装依赖。数据库、上传和结果继续使用既有持久卷。
