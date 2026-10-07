import "./InputValidationGuidance.css";

const guidance: Record<string, {title: string; detail: string; action: string}> = {
  valid: {title:"确认本次分析输入",detail:"文件基础校验已通过。继续确认所选版本、列映射、样本范围和分组，再检查是否可以运行。",action:"检查映射与开始分析"},
  needs_mapping: {title:"确认列与样本映射",detail:"请进入配置选择工作表、确认列和样本对应关系。整理文件会单独保存，原始输入保留。",action:"确认列与样本映射"},
  invalid: {title:"检查校验提示并修正输入",detail:"请根据提示检查必需列和数据值；可先进入配置确认映射。需要修改文件内容时，更新当前版本并保留历史来源。",action:"检查输入配置"},
  failed: {title:"重新校验或检查输入配置",detail:"本次校验未完成，可重新校验。仍失败时请查看错误详情，并确认文件格式、工作表和输入配置。",action:"检查输入配置"},
  pending: {title:"等待校验，同时确认输入配置",detail:"此文件正在校验，请勿重复提交校验。可先预览或进入配置确认映射；运行前会再次检查输入。",action:"先查看输入配置"},
  needs_refresh: {title:"重新校验并识别样本",detail:"此文件保留的是旧校验报告。请重新校验以识别当前样本，再确认列映射、样本登记和所需分析输入。",action:"检查输入配置"},
  unknown: {title:"确认映射并检查输入",detail:"此文件尚未完成校验。请确认工作表、必需列及样本对应关系，再检查所选分析的输入要求。",action:"检查映射与开始分析"},
};

export function inputValidationAction(status: string) {
  return (guidance[status] || guidance.unknown).action;
}

export function InputValidationGuidance({status}: {status: string}) {
  const next=guidance[status] || guidance.unknown;
  return <div className="data-input-guidance" role="status">
    <strong>下一步：{next.title}</strong><p>{next.detail}</p>
  </div>;
}
