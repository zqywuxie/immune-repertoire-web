import {useState} from "react";
import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,within} from "@testing-library/react";
import {GroupValueEditor} from "../features/projects/GroupValueEditor";
afterEach(cleanup);
const values=Array.from({length:1500},(_,i)=>`组${String(i).padStart(4,"0")}`);
function Harness({save}:{save:(values:string[])=>void}){
 const [order,setOrder]=useState(values);
 return <><GroupValueEditor values={values} order={order} onChange={setOrder} countLabel={()=>"1 个样本编号"} disabled={false}/><button onClick={()=>save(order)}>验收完整方案</button></>;
}
it("1500组的候选与顺序限量显示，搜索隐藏项仍参与完整保存",()=>{
 const save=vi.fn();render(<Harness save={save}/>);
 expect(screen.getAllByRole("checkbox")).toHaveLength(20);
 expect(within(screen.getByRole("list",{name:"分组展示顺序"})).getAllByRole("listitem")).toHaveLength(20);
 fireEvent.change(screen.getByRole("textbox",{name:"搜索可选分组"}),{target:{value:"组1499"}});
 fireEvent.click(screen.getByRole("checkbox",{name:/组1499/}));
 fireEvent.change(screen.getByRole("textbox",{name:"搜索可选分组"}),{target:{value:""}});
 fireEvent.click(screen.getByRole("button",{name:"验收完整方案"}));
 expect(save.mock.calls[0][0]).toHaveLength(1499);expect(save.mock.calls[0][0]).not.toContain("组1499");expect(save.mock.calls[0][0]).toContain("组1000");
});
it("搜索定位第1500组并移至全局首位，保存的其余成员与顺序保持",()=>{
 const save=vi.fn();render(<Harness save={save}/>);
 fireEvent.change(screen.getByRole("textbox",{name:"搜索已选分组"}),{target:{value:"组1499"}});
 expect(screen.getByRole("list",{name:"分组展示顺序"}).firstElementChild).toHaveTextContent("1500. 组1499");
 fireEvent.change(screen.getByRole("spinbutton",{name:"将 组1499 移到第几位"}),{target:{value:"1"}});
 fireEvent.click(screen.getByRole("button",{name:"移动 组1499"}));
 fireEvent.change(screen.getByRole("textbox",{name:"搜索已选分组"}),{target:{value:""}});
 expect(screen.getByRole("list",{name:"分组展示顺序"}).firstElementChild).toHaveTextContent("1. 组1499");
 fireEvent.click(screen.getByRole("button",{name:"验收完整方案"}));expect(save.mock.calls[0][0]).toEqual(["组1499",...values.slice(0,-1)]);
});
it("页首上移跨显示窗口按完整顺序处理，并显示目标所在页",()=>{
 const save=vi.fn();render(<Harness save={save}/>);
 fireEvent.click(screen.getByRole("button",{name:"已选分组下一页"}));
 expect(screen.getByRole("list",{name:"分组展示顺序"}).firstElementChild).toHaveTextContent("21. 组0020");
 fireEvent.click(screen.getByRole("button",{name:"上移 组0020"}));
 expect(screen.getByRole("list",{name:"分组展示顺序"})).toHaveTextContent("20. 组0020");
 fireEvent.click(screen.getByRole("button",{name:"验收完整方案"}));
 const expected=[...values];[expected[19],expected[20]]=[expected[20],expected[19]];expect(save.mock.calls[0][0]).toEqual(expected);
});
