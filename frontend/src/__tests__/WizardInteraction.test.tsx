import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { useApi } from "../shared/hooks/useApi";
import { Stage3ModuleConfig } from "../features/scripthub/stages/Stage3ModuleConfig";
import { Stage1DataIntake } from "../features/scripthub/stages/Stage1DataIntake";

vi.mock("../features/jobs/forms", () => ({ getFormComponent: () => null }));
vi.mock("../shared/api/projects", () => ({ listProjects: vi.fn().mockResolvedValue({projects:[{id:'p1',name:'项目'}]}), listProjectAssets: vi.fn().mockResolvedValue({assets:[]}), getProject: vi.fn().mockResolvedValue(null) }));
afterEach(cleanup);

describe("wizard data isolation",()=>{
  it("ignores an earlier project response that finishes last",async()=>{
    let resolveOld!: (data:string)=>void;
    const first=new Promise<string>(resolve=>{resolveOld=resolve;});
    const hook=renderHook(({id})=>useApi(()=>id==='old'?first:Promise.resolve('new-project'),[id]),{initialProps:{id:'old'}});
    hook.rerender({id:'new'});
    await waitFor(()=>expect(hook.result.current).toMatchObject({status:'ready',data:'new-project'}));
    await act(async()=>{resolveOld('old-project');});
    expect(hook.result.current).toMatchObject({status:'ready',data:'new-project'});
  });
  it("ignores an earlier failure after a manual refresh succeeds",async()=>{
    let rejectOld!: (reason:Error)=>void;
    const first=new Promise<string>((_,reject)=>{rejectOld=reject;});
    const fetcher=vi.fn().mockReturnValueOnce(first).mockResolvedValue('refreshed');
    const hook=renderHook(()=>useApi(fetcher,[]));
    act(()=>hook.result.current.refetch());
    await waitFor(()=>expect(hook.result.current).toMatchObject({data:'refreshed'}));
    await act(async()=>{rejectOld(new Error('old failure'));});
    expect(hook.result.current).toMatchObject({status:'ready',data:'refreshed'});
  });
  it("retains the dataset name when returning and removing a PEP path",async()=>{
    const update=vi.fn();
    render(<Stage1DataIntake projectId="p1" assetSetName="Set2" pepPaths={['/pep.csv']} profilePath="/profile.csv" transcriptomePath="" onUpdate={update}/>);
    await waitFor(()=>expect(screen.getByText('/pep.csv')).toBeInTheDocument());
    const remove=screen.getByText('/pep.csv').closest('div')?.parentElement?.querySelector('button');
    expect(remove).toBeTruthy();
    fireEvent.click(remove!);
    expect(update).toHaveBeenLastCalledWith(expect.objectContaining({assetSetName:'Set2',profilePath:'/profile.csv',pepPaths:[]}));
  });
});

describe('module discovery',()=>{
  it('filters available modules without changing the selected configuration',()=>{
    const onUpdate=vi.fn();
    render(<Stage3ModuleConfig modules={[{key:'profile',label:"样本指标表 指标"},{key:'charts',label:'综合图表'}]} projectId="" selectedModules={['profile']} moduleConfigs={{profile:{metric:'keep'}}} sourceContext={{profilePath:'/profile.csv'} as never} onUpdate={onUpdate}/>);
    expect(screen.getByRole('button',{name:'配置 综合图表'})).toHaveAttribute('aria-disabled','true');
    fireEvent.click(screen.getByRole('checkbox',{name:'只显示当前可运行模块'}));
    expect(screen.queryByRole('button',{name:'配置 综合图表'})).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox'),{target:{value:'no match'}});
    expect(screen.getByRole('status')).toHaveTextContent('没有匹配');
    expect(screen.getByText('已选 1 个模块')).toBeInTheDocument();
    expect(onUpdate).not.toHaveBeenCalled();
  });
});
