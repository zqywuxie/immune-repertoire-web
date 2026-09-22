import {useState} from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {InfiltrationConfig} from '../features/scripthub/modules/InfiltrationConfig';
afterEach(()=>vi.unstubAllGlobals());
it('核对当前项目范围，修改细胞后使确认失效',async()=>{
  const calls:Record<string,unknown>[]=[];
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const body=JSON.parse(String(init?.body||'{}'));
    if(String(input).includes('immune-infiltration'))calls.push(body);
    return new Response(JSON.stringify({success:true,cell_columns:['T cells','B cells'],sample_count:8,values:['甲','乙'],group_counts:body.group_field?{'甲':4,'乙':4}:undefined,unused_profile_count:1}),{headers:{'content-type':'application/json'}});
  }));
  function Harness(){
    const [value,setValue]=useState<Record<string,unknown>>({group_field:'group'});
    return <><InfiltrationConfig projectId="project" module="immune-infiltration" groupSpecs={[]} loadingSpecs={false} value={value} onChange={setValue} sourceContext={{assetSetId:'batch',profilePath:'/profile.csv',deconvolutionPath:'/deconv.csv',sampleNames:[],chains:[],profileFields:['sample','group'],groupFields:['group'],pepColumns:[]}}/><output data-testid="ready">{String(value.infiltration_checked)}</output></>;
  }
  render(<Harness/>);
  await waitFor(()=>expect(screen.getByRole('radio',{name:'相对比例'})).toBeEnabled());
  expect(screen.getByRole('button',{name:'核对分析范围'})).toBeDisabled();
  fireEvent.click(screen.getByRole('radio',{name:'相对比例'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'核对分析范围'})).toBeEnabled());
  expect(screen.getByTestId('ready')).toHaveTextContent('false');
  fireEvent.click(screen.getByRole('button',{name:'核对分析范围'}));
  await waitFor(()=>expect(screen.getByTestId('ready')).toHaveTextContent('true'));
  expect(calls.at(-1)).toEqual(expect.objectContaining({project_id:'project',asset_set:'batch',deconvolution_path:'/deconv.csv',group_field:'group',cell_columns:['T cells','B cells'],score_type:'relative'}));
  expect(screen.getByText('甲：4 个；乙：4 个')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('radio',{name:'绝对分数'}));
  expect(screen.getByTestId('ready')).toHaveTextContent('false');
  fireEvent.click(screen.getByRole('button',{name:'核对分析范围'}));
  await waitFor(()=>expect(screen.getByTestId('ready')).toHaveTextContent('true'));
  expect(calls.at(-1)?.score_type).toBe('absolute');
  fireEvent.click(screen.getByRole('checkbox',{name:'T cells'}));
  expect(screen.getByTestId('ready')).toHaveTextContent('false');
  expect(screen.queryByText('甲：4 个；乙：4 个')).not.toBeInTheDocument();
});
