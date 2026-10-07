import {useState} from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,render,screen,fireEvent,waitFor} from '@testing-library/react';
import {submitLegacyScriptHubJob} from '../shared/api/scriptHub';
import {InfiltrationConfig} from '../features/scripthub/modules/InfiltrationConfig';
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
it.each(['immune-infiltration','immune-infiltration-consistency','immune-infiltration-concordance','immune-infiltration-paired','immune-infiltration-pathway','immune-infiltration-sample-pathway'])('%s：核对当前项目范围，修改参数后使确认失效',async(analysisModule)=>{
  const calls:Record<string,unknown>[]=[];
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    if(String(input).includes('/sources'))return new Response(JSON.stringify({candidates:[{id:'go:0',job_id:'go',status:'available',reason:'',comparison:{group1:'甲',group2:'乙'}},{id:'old',job_id:'old',status:'unavailable',reason:'来源没有完整通路表',comparison:{group1:'乙',group2:'甲'}}]}),{headers:{'content-type':'application/json'}});
    const body=JSON.parse(String(init?.body||'{}'));
    if(String(input).includes('immune-infiltration'))calls.push(body);
    return new Response(JSON.stringify({success:true,cell_columns:['T cells','B cells'],subclass_columns:['IGHA1'],profile_samples:['001','002'],deconvolution_samples:['001','002'],sample_count:8,values:['甲','乙'],comparison_groups:['甲','乙'],expression_match_count:8,unused_expression_sample_count:1,group_counts:body.group_field?{'甲':4,'乙':4}:undefined,unused_profile_count:1}),{headers:{'content-type':'application/json'}});
  }));
  function Harness(){
    const [value,setValue]=useState<Record<string,unknown>>({group_field:'group'});
    return <><InfiltrationConfig projectId="project" module={analysisModule} groupSpecs={[]} loadingSpecs={false} value={value} onChange={setValue} sourceContext={{assetSetId:'batch',profilePath:'/profile.csv',deconvolutionPath:'/deconv.csv',transcriptomePath:'/expression.csv',sampleNames:[],chains:[],profileFields:['sample','group'],groupFields:['group'],pepColumns:[]}}/><output data-testid="ready">{String(value.infiltration_checked)}</output></>;
  }
  render(<Harness/>);
  await waitFor(()=>expect(screen.getByRole('radio',{name:'相对比例'})).toBeEnabled());
  expect(screen.getByRole('button',{name:'核对分析范围'})).toBeDisabled();
  fireEvent.click(screen.getByRole('radio',{name:'相对比例'}));
  if(analysisModule==='immune-infiltration-pathway'){
    expect(screen.getByRole('button',{name:'核对分析范围'})).toBeDisabled();
    await waitFor(()=>expect(screen.getByRole('radio',{name:'甲 相对于 乙 · go'})).toBeEnabled());
    expect(screen.getByRole('radio',{name:'乙 相对于 甲 · old'})).toBeDisabled();
    expect(screen.getByText('来源没有完整通路表')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio',{name:'甲 相对于 乙 · go'}));
  }
  if(analysisModule==='immune-infiltration-sample-pathway'){
    expect(screen.getByRole('button',{name:'核对分析范围'})).toBeDisabled();
    await waitFor(()=>expect(screen.getByRole('combobox',{name:'第 1 组'})).toBeEnabled());
    fireEvent.change(screen.getByRole('combobox',{name:'第 1 组'}),{target:{value:'甲'}});
    fireEvent.change(screen.getByRole('combobox',{name:'第 2 组'}),{target:{value:'乙'}});
    expect(screen.getByRole('button',{name:'核对分析范围'})).toBeEnabled();
  }
  if(analysisModule==='immune-infiltration-paired'){
    expect(screen.getByRole('button',{name:'核对分析范围'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button',{name:'按完全相同编号填写'}));
  }
  await waitFor(()=>expect(screen.getByRole('button',{name:'核对分析范围'})).toBeEnabled());
  expect(screen.getByTestId('ready')).toHaveTextContent('false');
  fireEvent.click(screen.getByRole('button',{name:'核对分析范围'}));
  await waitFor(()=>expect(screen.getByTestId('ready')).toHaveTextContent('true'));
  expect(calls.at(-1)).toEqual(expect.objectContaining({project_id:'project',asset_set:'batch',deconvolution_path:'/deconv.csv',group_field:'group',cell_columns:['T cells','B cells'],score_type:'relative'}));
  if(analysisModule==='immune-infiltration-sample-pathway')expect(calls.at(-1)).toEqual(expect.objectContaining({transcriptome_path:'/expression.csv',comparison:['甲','乙']}));
  expect(screen.getByText('甲：4 个；乙：4 个')).toBeInTheDocument();
  if(analysisModule==='immune-infiltration-pathway'){
    expect(calls.at(-1)).toEqual(expect.objectContaining({upstream_artifact_id:'go:0',comparison:['甲','乙']}));
    fireEvent.click(screen.getByRole('button',{name:'刷新来源'}));
    expect(screen.getByTestId('ready')).toHaveTextContent('false');
    await waitFor(()=>expect(screen.getByRole('radio',{name:'甲 相对于 乙 · go'})).toBeEnabled());
    expect(screen.getByRole('radio',{name:'甲 相对于 乙 · go'})).toBeChecked();
    fireEvent.click(screen.getByRole('radio',{name:'甲 相对于 乙 · go'}));
  }
  if(analysisModule==='immune-infiltration-paired'){
    expect(calls.at(-1)?.sample_pairs).toEqual([{deconvolution_sample:'001',profile_sample:'001'},{deconvolution_sample:'002',profile_sample:'002'}]);
    fireEvent.change(screen.getByRole('combobox',{name:'指标样本：001'}),{target:{value:'002'}});
    expect(screen.getByTestId('ready')).toHaveTextContent('false');
    expect(screen.getByRole('alert')).toHaveTextContent('重复使用指标样本 1 项');
    fireEvent.change(screen.getByRole('combobox',{name:'指标样本：001'}),{target:{value:'001'}});
  }
  if(analysisModule==='immune-infiltration-concordance'){
    expect(calls.at(-1)?.subclass_columns).toEqual(['IGHA1']);
    fireEvent.click(screen.getByRole('checkbox',{name:'IGHA1'}));
    expect(screen.getByTestId('ready')).toHaveTextContent('false');
    expect(screen.getByRole('button',{name:'核对分析范围'})).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox',{name:'IGHA1'}));
  }
  fireEvent.click(screen.getByRole('radio',{name:'绝对分数'}));
  expect(screen.getByTestId('ready')).toHaveTextContent('false');
  await waitFor(()=>expect(screen.getByRole('button',{name:'核对分析范围'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'核对分析范围'}));
  await waitFor(()=>expect(screen.getByTestId('ready')).toHaveTextContent('true'));
  expect(calls.at(-1)?.score_type).toBe('absolute');
  fireEvent.click(screen.getByRole('checkbox',{name:'T cells'}));
  expect(screen.getByTestId('ready')).toHaveTextContent('false');
  expect(screen.queryByText('甲：4 个；乙：4 个')).not.toBeInTheDocument();
});

const context={assetSetId:'Set2',profilePath:'/profile.csv',deconvolutionPath:'/deconv.csv',sampleNames:[],chains:[],profileFields:['sample','group'],groupFields:['group'],pepColumns:[]};
function SavedHarness({observe=vi.fn(),initial={},source=context}:{observe?:(next:Record<string,unknown>)=>void;initial?:Record<string,unknown>;source?:typeof context}){
  const [value,setValue]=useState<Record<string,unknown>>(initial);
  return <InfiltrationConfig projectId="project" module="immune-infiltration" groupSpecs={[]} loadingSpecs={false}
    value={value} onChange={next=>{setValue(next);observe(next);}} sourceContext={source}/>;
}
const reply=(data:unknown)=>new Response(JSON.stringify(data),{headers:{'content-type':'application/json'}});
it('preserves saved choices and output edits during initial inspection',async()=>{
  let done!:(response:Response)=>void;
  vi.stubGlobal('fetch',vi.fn(()=>new Promise<Response>(resolve=>{done=resolve;})));
  const observe=vi.fn();render(<SavedHarness observe={observe} initial={{cell_columns:['B cells'],subclass_columns:['IGHA1'],sample_pairs:[{deconvolution_sample:'甲::001',profile_sample:'P001'}],comparison:['02','01'],upstream_artifact_id:'saved'}}/>);
  fireEvent.change(screen.getByLabelText('输出名称'),{target:{value:'保留我的名称'}});
  await act(async()=>done(reply({success:true,cell_columns:['T cells','B cells'],sample_count:8})));
  expect(observe.mock.calls.at(-1)?.[0]).toMatchObject({output_name:'保留我的名称',cell_columns:['B cells'],comparison:['02','01'],upstream_artifact_id:'saved',sample_pairs:[{deconvolution_sample:'甲::001',profile_sample:'P001'}]});
  expect(screen.getByRole('checkbox',{name:'B cells'})).toBeChecked();expect(screen.getByRole('checkbox',{name:'T cells'})).not.toBeChecked();
});
it('checks actual matched identities and clears choices only when source changes',async()=>{
  const groups={'01':['甲::001','甲::002','甲::003'],'02':['乙::001','乙::002','乙::003']};
  const calls:Record<string,unknown>[]=[];
  vi.stubGlobal('fetch',vi.fn(async(_url:unknown,init?:RequestInit)=>{
    const body=JSON.parse(String(init?.body||'{}'));calls.push(body);
    if(String(_url).endsWith('/jobs'))return reply({success:true,task_id:'synthetic-only'});
    return reply({success:true,cell_columns:['T cells','B cells'],sample_count:6,samples_by_value:body.group_field?groups:undefined,
      group_counts:body.group_field?{'01':3,'02':3}:undefined});
  }));
  const observe=vi.fn(),view=render(<SavedHarness observe={observe} initial={{group_field:'group',score_type:'relative',cell_columns:['B cells'],output_name:'我的浸润'}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'01 / 甲 / 001'}));
  expect(observe.mock.calls.at(-1)?.[0].selected_infiltration_samples).toEqual(['甲::002','甲::003','乙::001','乙::002','乙::003']);
  await waitFor(()=>expect(screen.getByRole('button',{name:'核对分析范围'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'核对分析范围'}));
  await screen.findByText(/分析范围已确认/);
  expect(calls.at(-1)).toMatchObject({selected_infiltration_samples:['甲::002','甲::003','乙::001','乙::002','乙::003'],cell_columns:['B cells']});
  await submitLegacyScriptHubJob({module:'immune-infiltration',projectId:'project',payload:{...observe.mock.calls.at(-1)?.[0],asset_set:'Set2',selected_samples:['unused'],selected_group_values:{old:['unknown']}}});
  expect(calls.at(-1)).toMatchObject({selected_infiltration_samples:['甲::002','甲::003','乙::001','乙::002','乙::003']});
  expect(calls.at(-1)?.selected_samples).toBeUndefined();expect(calls.at(-1)?.selected_group_values).toBeUndefined();
  view.rerender(<SavedHarness observe={observe} source={{...context,assetSetId:'Set3'}}/>);
  await waitFor(()=>expect(observe.mock.calls.at(-1)?.[0].selected_infiltration_samples).toBeUndefined());
  expect(screen.getByLabelText('输出名称')).toHaveValue('我的浸润');
  expect(observe.mock.calls.at(-1)?.[0].infiltration_checked).toBe(false);
});
