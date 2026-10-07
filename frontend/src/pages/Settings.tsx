import "../features/assets/StorageUsage.css";
import { Select } from "../shared/components/Select";
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { Save, RotateCcw } from "lucide-react";
import { PageHeader } from "../shared/components/PageHeader";
import { Card } from "../shared/components/Card";
import { useApi } from "../shared/hooks/useApi";
import { apiClient } from "../shared/api/client";

type Config = { default_figure_size: number[]; default_font_size: number; default_dpi: number; [key: string]: unknown };
const DEFAULTS: Config = { default_figure_size: [10, 8], default_font_size: 12, default_dpi: 300 };
export function Settings() {
  const workspace = useLocation().pathname.startsWith('/management') ? 'management' : 'analysis';
  return <WorkspaceSettings key={workspace} workspace={workspace} />;
}
function WorkspaceSettings({ workspace }: { workspace: string }) {
  const [config, setConfig] = useState<Config>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    apiClient.get<{ config: Config }>('/api/config', { config_id: workspace }, { skipCache: true })
      .then(data => { if (active) setConfig({ ...DEFAULTS, ...data.config }); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : '读取设置失败'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [workspace, revision]);
  const change = (values: Partial<Config>) => { setConfig(previous => ({ ...previous, ...values })); setMessage('有未保存的修改'); };
  async function save(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setError(''); setMessage('');
    try {
      const response = await apiClient.post<{ success: boolean; config: Config }>('/api/config', { config_id: workspace, config });
      if (!response.success) throw new Error('保存失败，请重试');
      setConfig(response.config); apiClient.invalidatePath('/api/config'); setMessage('设置已保存到当前账户');
    } catch (reason) { setError(reason instanceof Error ? reason.message : '保存失败，请重试'); }
    finally { setSaving(false); }
  }
  return <>
    <PageHeader title={workspace === 'analysis' ? '分析设置' : '管理设置'} subtitle="保存当前账户的图表输出偏好" />
    <form onSubmit={save} style={{ display: 'grid', gap: 'var(--spacing-lg)', maxWidth: 900 }}>
      <Card>
        <h3>图表尺寸与导出质量</h3>
        <p style={{ color: 'var(--text-secondary)' }}>{workspace === 'analysis' ? '用于数据分析页面的方案图表。单次分析明确指定的参数优先；分析向导各模块使用各自的图表配置。' : '管理工作区的独立偏好；运行分析时使用“分析设置”。'}</p>
        <fieldset disabled={loading || saving} style={{ border: 0, padding: 0, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: 'var(--spacing-md)' }}>
          <label>图宽（英寸）<input className="input" type="number" required min={2} max={24} step={0.5} value={config.default_figure_size[0]} onChange={event => change({ default_figure_size: [Number(event.target.value), config.default_figure_size[1]] })} /></label>
          <label>图高（英寸）<input className="input" type="number" required min={2} max={24} step={0.5} value={config.default_figure_size[1]} onChange={event => change({ default_figure_size: [config.default_figure_size[0], Number(event.target.value)] })} /></label>
          <label>基础字号（pt）<input className="input" type="number" required min={6} max={36} value={config.default_font_size} onChange={event => change({ default_font_size: Number(event.target.value) })} /></label>
          <label>导出分辨率（DPI）<Select ariaLabel="导出分辨率" value={String(config.default_dpi)} disabled={loading || saving} onChange={value => change({default_dpi:Number(value)})} options={[72,150,300,600].map(value => ({value:String(value),label:`${value} DPI`}))} /></label>
        </fieldset>
        <p style={{ color: 'var(--text-secondary)' }}>PNG 图像；名义尺寸约 {Math.round(config.default_figure_size[0] * config.default_dpi)} × {Math.round(config.default_figure_size[1] * config.default_dpi)} 像素，实际边界随图表内容调整。</p>
      </Card>
      {loading && <p role="status">正在读取设置…</p>}
      {error && <div role="alert"><p style={{ color: 'var(--danger)' }}>{error}</p><button type="button" className="btn btn-secondary" onClick={() => setRevision(value => value + 1)}>重新读取</button></div>}
      {message && <p role="status">{message}</p>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--spacing-md)', justifyContent: 'flex-end' }}>
        <button className="btn btn-secondary" type="button" disabled={loading || saving} onClick={() => change(DEFAULTS)}><RotateCcw size={16} />恢复默认值</button>
        <button className="btn btn-primary" type="submit" disabled={loading || saving}><Save size={16} />{saving ? '正在保存…' : '保存设置'}</button>
      </div>
    </form>
    <StorageUsage />
  </>;
}


type RegisteredCategory={count:number;bytes:number};
type FilesystemCapacity={labels:string[];available:boolean;total_bytes?:number;used_bytes?:number;free_bytes?:number};
type StorageStatistics={files:number;assets:number;file_bytes:number;asset_bytes:number;registered_categories?:Record<string,RegisteredCategory>;filesystem_capacity?:FilesystemCapacity[];capacity_visible?:boolean;cache_bytes?:number|null};
const storageLabels:Record<string,string>={current_inputs:"当前分析输入",historical_inputs:"历史输入版本",results:"已登记分析结果",other:"其他项目文件"};
const formatStorageBytes=(bytes:number)=>{if(bytes<1024)return `${bytes} B`;if(bytes<1024**2)return `${(bytes/1024).toFixed(2)} KB`;if(bytes<1024**3)return `${(bytes/1024**2).toFixed(2)} MB`;return `${(bytes/1024**3).toFixed(2)} GB`;};
function StorageUsage() {
  const state=useApi(()=>apiClient.get<StorageStatistics>('/api/storage',undefined,{skipCache:true}),[]);
  return <Card className="storage-usage"><h3>已登记文件统计</h3>
    {state.status==='ready' ? <><p>已登记 {state.data.files} 个上传文件、{state.data.assets} 个项目文件，条目累计 {formatStorageBytes(state.data.file_bytes+state.data.asset_bytes)}。</p>
      {state.data.registered_categories && <dl className="storage-usage__categories">{Object.entries(state.data.registered_categories).map(([key,value])=><div className="storage-usage__category" key={key}><dt>{storageLabels[key] || "其他登记"}</dt><dd><strong>{value.count} 项</strong><span>{formatStorageBytes(value.bytes)}</span></dd></div>)}</dl>}
      {state.data.capacity_visible && <section className="storage-usage__capacity" aria-label="服务器文件系统容量"><h4>服务器文件系统容量</h4><p>以下为共享文件系统容量，包含其他目录和项目；同一文件系统合并显示，不是当前账户的占用或配额。</p>
        {(state.data.filesystem_capacity || []).map((item,index)=><div className="storage-usage__filesystem" key={index}><strong>{item.labels.join(" / ")}</strong>{item.available ? <dl>{([["总量",item.total_bytes],["已用",item.used_bytes],["可用",item.free_bytes]] as const).map(([label,bytes])=><div key={label}><dt>{label}</dt><dd>{typeof bytes==='number'?formatStorageBytes(bytes):"未记录"}</dd></div>)}</dl> : <p className="storage-usage__unknown">暂时无法读取</p>}</div>)}</section>}
    </> : <p role={state.status==='error'?'alert':'status'}>{state.status==='error'?state.error:'正在统计…'}</p>}
    <p>登记字节包含历史版本和结果；同一物理文件有多个登记时可能重复累计。缓存占用未单独统计，不能当作零；未登记的外部文件不在登记统计中。分析结果请通过任务生命周期处理。</p>
    <button className="btn btn-secondary" onClick={state.refetch}>刷新存储统计</button>
  </Card>;
}
