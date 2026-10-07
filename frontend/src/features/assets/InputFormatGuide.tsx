import {Download} from "lucide-react";

export const inputExamples = [
  {kind:"pep",name:"克隆序列表",filename:"001__TRB.csv",note:"每个文件对应一个样本与链；例如 001__TRB.csv。克隆序列、V/J 和丰度列可在导入后映射。",
    csv:"CDR3(pep),V,J,copy\nCASSLGQETQYF,TRBV7-9,TRBJ2-5,10\nCASSIRSSYEQYF,TRBV19,TRBJ2-7,5\n"},
  {kind:"profile",name:"样本指标表",filename:"样本指标表示例.csv",note:"每行一个样本，包含样本编号、分组及所需指标。可自定义分组和指标列名；001 等编号应保留文本。",
    csv:"sample,group,指标值\n001,健康,1.2\n002,疾病,2.5\n"},
  {kind:"transcriptome",name:"转录组",filename:"转录组示例.csv",note:"默认每行一个基因、每列一个样本，首列为基因编号。样本在行的矩阵也可导入，须在映射时明确方向。",
    csv:"Gene,001,002\nTP53,12,18\nCD3D,7,11\n"},
  {kind:"deconvolution",name:"免疫细胞浸润",filename:"免疫细胞浸润示例.csv",note:"每行一个样本，首列为样本编号，其余列为细胞类型数值。支持浸润分析结果中的样本标识列。",
    csv:"sample,T细胞,B细胞\n001,0.7,0.3\n002,0.4,0.6\n"},
];

export function InputFormatGuide({kind}:{kind:string}) {
  const examples=inputExamples.filter(item=>!kind || item.kind===kind);
  return <details className="data-format-guide"><summary>查看输入格式与示例文件</summary>
    <p className="data-muted">示例仅说明表结构，请替换为真实数据；四类输入按分析需要提供。下载列名对应当前解析规则。</p>
    {examples.map(item=><section key={item.kind} aria-label={`${item.name}格式说明`}>
      <h4>{item.name}</h4><p>{item.note}</p>
      <pre>{item.csv.trim()}</pre>
      <a className="btn btn-secondary" href={`data:text/csv;charset=utf-8,${encodeURIComponent("\uFEFF"+item.csv)}`} download={item.filename}>
        <Download size={15}/>下载{item.name}示例</a>
    </section>)}
  </details>;
}
