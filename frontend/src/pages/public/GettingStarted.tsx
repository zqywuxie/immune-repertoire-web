import { Link } from 'react-router-dom';
const profile='sample,group,TRA_reads,TRB_reads,diversity\nS1,Control,120,90,2.1\nS2,Control,135,95,2.3\nS3,Control,125,92,2.2\nS4,Treatment,180,110,2.8\nS5,Treatment,190,120,2.9\nS6,Treatment,185,115,2.7\n';
const pep='CDR3(pep),V,J,copy\nCAVRDSNYQLIW,TRAV1-2,TRAJ33,120\nCAVMDSNYQLIW,TRAV1-2,TRAJ33,30\nCAVRPGGAGPFF,TRAV12-2,TRAJ23,10\n';
export function GettingStarted(){return <main style={{maxWidth:1000,margin:'0 auto',padding:'40px clamp(16px,4vw,48px)',lineHeight:1.8}}>
  <Link to="/">返回工作台</Link><h1>从第一份数据开始</h1><p>先用合成示例熟悉操作，再上传自己的科研数据。示例仅用于演示，不代表真实实验结论。</p>
  <ol><li><Link to="/management/projects">创建项目</Link>，填写项目名称。</li><li>进入<Link to="/analysis/center">分析中心</Link>，选择项目并上传 样本指标表 或 克隆序列表 数据。</li><li>按科研问题选择工具，检查样本、链类型和列名，再配置分组字段。</li><li>提交任务，完成后查看报告、下载图表及分析记录；离开页面后可在任务中心继续查看。</li></ol>
  <h2>输入模板</h2><div style={{display:'flex',flexWrap:'wrap',gap:16}}><a className="btn btn-primary" download="Profile_demo.csv" href={'data:text/csv;charset=utf-8,'+encodeURIComponent('\ufeff'+profile)}>下载 样本指标表 示例</a><a className="btn btn-secondary" download="S1__TRA.csv" href={'data:text/csv;charset=utf-8,'+encodeURIComponent('\ufeff'+pep)}>下载 克隆序列表 示例</a></div>
  <p>样本指标表：每行一个样本，sample 为唯一标识，group 为分组，其他列为数值指标。克隆序列表：每个样本与链分别一个文件，包含 CDR3 氨基酸序列、V/J 基因和非负计数；示例文件名为 S1__TRA.csv。</p>
  <p>样本指标表 示例可直接用于<Link to="/analysis/statistical">统计比较</Link>：数值列选择 diversity，分组列选择 group。做跨样本共享分析时，需要每个样本各自的 克隆序列表 文件。</p>
  <h2>根据研究问题选择分析</h2><div style={{overflowX:'auto'}}><table style={{width:'100%',textAlign:'left'}}><thead><tr><th>参考目录</th><th>平台入口 / 当前覆盖</th><th>主要输入</th></tr></thead><tbody>
  {[
    ["01 样本指标",'Profile 指标、箱线图与分组统计','Profile'],["02 免疫球蛋白",'数据分析中的 B 细胞同型方案；CSR 专项流程尚未接入','同型指标表'],
    ["03 唯一克隆序列",'PEP 共享、TopClone、MAIT/NKT、Pgen','PEP + Profile；Pgen 还需模型依赖'],["04 数据库比对",'数据库比对','PEP + Profile + 参考数据库'],
    ["05 基因特征",'V/J 使用情况与火山图','PEP 分析产生的使用频率表'],["06 转录组",'GO/KEGG 富集','表达矩阵 + 分组；需要 R 环境'],
    ["07 免疫浸润",'尚未接入网页分析','转录组与对应参考数据'],["08 聚类",'尚未接入网页分析','克隆序列及相关注释'],
    ["09 机器学习",'机器学习分析','特征矩阵 + 标签'],["10 降维","样本与特征降维",'数值特征与分组信息']
  ].map(row=><tr key={row[0]}>{row.map((value,index)=><td key={index} style={{padding:'12px 8px',borderBottom:'1px solid var(--separator)'}}>{value}</td>)}</tr>)}
  </tbody></table></div><p>各模块的输入与参数以检查页面为准；上述覆盖表示已有入口，不代表与参考目录全部脚本逐项等同。</p>
  <h2>常见问题</h2><dl><dt>模块不可运行？</dt><dd>查看卡片上的缺失数据提示。仅上传 样本指标表 时，可先运行 样本指标表 指标分析。</dd><dt>分组为空？</dt><dd>检查样本标识是否一致、group 列是否包含有效值；不要把每个样本都当成一个组。</dd><dt>任务失败？</dt><dd>在任务中心查看具体原因，修改参数后重新运行；结果读取失败可以直接重试。</dd><dt>下载什么文件用于科研记录？</dt><dd>保留原始输入、统计 CSV、图表和分析记录 JSON。报告中的 p/q 值以实际使用的检验及校正方法为准。</dd></dl>
  <Link className="btn btn-primary" to="/analysis/center">进入分析中心</Link>
</main>;}
