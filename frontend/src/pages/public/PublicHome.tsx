import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Dna, BarChart3, Layers, GitCompareArrows, Upload, SlidersHorizontal, Download } from "lucide-react";
import "./PublicHome.css";

const capabilities = [
  { icon: BarChart3, title: "样本指标与组间比较", input: "Profile 指标表", text: "选择分组、样本和指标，生成箱线图与统计结果。" },
  { icon: Layers, title: "克隆组成与基因使用", input: "PEP 克隆数据", text: "从 TopClone、克隆分布和 V/J 使用情况观察组库组成。" },
  { icon: GitCompareArrows, title: "样本相似性与可视化", input: "多样本克隆数据", text: "通过相似性热图、矩形树图和弦图展示样本特征。" },
];
const example = { A: [32, 23, 18, 12, 9, 6], B: [18, 17, 17, 16, 16, 16] };

export function PublicHome() {
  const [sample, setSample] = useState<"A" | "B">("A");
  return <div className="public-home">
    <a className="home-skip" href="#main-content">跳到主要内容</a>
    <header className="home-header">
      <Link className="home-brand" to="/" aria-label="免疫组库分析平台首页"><Dna size={26} /><span>免疫组库<span className="home-brand-sub">分析平台</span></span></Link>
      <nav aria-label="首页导航"><a href="#capabilities">分析能力</a><a href="#workflow">使用流程</a><a href="#example">示例预览</a></nav>
      <Link className="home-login" to="/management">进入工作台 <ArrowRight size={16} /></Link>
    </header>
    <main id="main-content">
      <section className="home-hero">
        <div className="home-hero-copy">
          <p className="home-eyebrow">免疫组库分析</p>
          <h1>从免疫组库数据，<br />走向清晰的研究结果。</h1>
          <p className="home-intro">整理样本、比较分组、探索克隆特征。将分析参数与结果放在同一个工作流程中，让每一步都有据可查。</p>
          <div className="home-actions"><Link className="home-primary" to="/analysis/script-hub">开始分析 <ArrowRight size={18} /></Link><a className="home-secondary" href="#example">先看示例</a></div>
          <p className="home-footnote">中文操作引导 · 项目化管理 · 图表与数据导出</p>
        </div>
        <div className="home-preview" id="example">
          <div className="home-preview-heading"><div><p className="home-eyebrow">结果预览</p><h2>克隆频率分布</h2></div><span className="home-tag">合成示例</span></div>
          <div className="home-sample-switch" aria-label="选择示例样本">{(["A", "B"] as const).map(key => <button key={key} aria-pressed={sample === key} onClick={() => setSample(key)}>样本 {key}</button>)}</div>
          <div className="home-chart" role="img" aria-label={`样本 ${sample} 的 6 个克隆频率依次为 ${example[sample].join('、')}%，总和 100%`}>
            <div className="home-chart-label">克隆频率（%）</div>
            <div className="home-bars">{example[sample].map((value, i) => <div className="home-bar-column" key={i}><span>{value}%</span><div className="home-bar" style={{ height: `${value * 4}px`, opacity: 1 - i * .1 }} /><small>C{i + 1}</small></div>)}</div>
          </div>
          <div className="home-preview-note">示例展示两个合成样本的频率分布，可切换查看；不代表真实研究结果。</div>
        </div>
      </section>
      <section className="home-section" id="capabilities">
        <div className="home-section-heading"><div><p className="home-eyebrow">分析能力</p><h2>围绕你的研究问题，选择分析</h2></div><Link to="/analysis/script-hub">打开分析向导 <ArrowRight size={16} /></Link></div>
        <div className="home-capabilities">{capabilities.map(({ icon: Icon, title, input, text }, i) => <article key={title}><div className="home-capability-top"><Icon size={24} /><span>0{i + 1}</span></div><h3>{title}</h3><p>{text}</p><div className="home-input-label">输入 · {input}</div></article>)}</div>
      </section>
      <section className="home-section home-workflow" id="workflow">
        <div><p className="home-eyebrow">从这里开始</p><h2>把分析过程，<br />分成清楚的三步。</h2><p>第一次使用？先创建项目，再上传一份 样本指标表 指标表。</p><Link to="/management/projects">创建或选择项目 <ArrowRight size={16} /></Link></div>
        <ol>{[{ icon: Upload, title: "上传并确认数据", text: "文件上传至平台，按项目与数据集整理；确认样本和字段识别结果。" }, { icon: SlidersHorizontal, title: "选择分组与分析参数", text: "明确参与比较的样本、分组字段与指标，检查后提交分析任务。" }, { icon: Download, title: "查看报告与下载结果", text: "等待任务完成，查看生成的报告，并下载可用的图表和数据文件。" }].map(({ icon: Icon, title, text }, i) => <li key={title}><span className="home-step">0{i + 1}</span><div><h3><Icon size={18} />{title}</h3><p>{text}</p></div></li>)}</ol>
      </section>
    </main>
    <footer className="home-footer"><span>免疫组库分析平台</span><span>TCR / BCR · 科研数据分析</span><a href="#main-content">返回顶部 ↑</a></footer>
  </div>;
}
