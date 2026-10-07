import {useEffect, useRef} from "react";
import "./Tabs.css";
type Tab = {key:string;label:string;secondary?:boolean};
export function Tabs({tabs,activeKey,onChange}:{tabs:Tab[];activeKey:string;onChange:(key:string)=>void}) {
  const list = useRef<HTMLDivElement>(null);
  const buttons = useRef(new Map<string,HTMLButtonElement>());
  const keys = tabs.map(tab=>tab.key).join("|");
  function reveal(button:HTMLButtonElement | undefined) {
    const container=list.current;if (!container || !button) return;
    const view=container.getBoundingClientRect(),item=button.getBoundingClientRect();
    if (item.left<view.left+8) container.scrollLeft-=view.left+8-item.left;
    else if (item.right>view.right-8) container.scrollLeft+=item.right-view.right+8;
  }
  useEffect(()=>{
    const selected=()=>reveal(buttons.current.get(activeKey));selected();
    const observer=typeof ResizeObserver!=="undefined" ? new ResizeObserver(selected) : null;
    if (list.current)observer?.observe(list.current);
    window.addEventListener("resize",selected);
    return ()=>{observer?.disconnect();window.removeEventListener("resize",selected);};
  },[activeKey,keys]);
  function focus(index:number) {const button=buttons.current.get(tabs[index]?.key);button?.focus({preventScroll:true});reveal(button);}
  return <div className="workspace-tabs" ref={list} role="tablist">
    {tabs.map((tab,index)=><button key={tab.key} type="button" role="tab" aria-selected={activeKey===tab.key}
      className={tab.secondary ? "workspace-tab is-secondary" : "workspace-tab"} tabIndex={activeKey===tab.key ? 0 : -1}
      ref={element=>{if(element)buttons.current.set(tab.key,element);else buttons.current.delete(tab.key);}}
      onClick={()=>onChange(tab.key)} onKeyDown={event=>{
        const target=event.key==="ArrowLeft" ? (index+tabs.length-1)%tabs.length : event.key==="ArrowRight" ? (index+1)%tabs.length
          : event.key==="Home" ? 0 : event.key==="End" ? tabs.length-1 : -1;
        if(target>=0){event.preventDefault();focus(target);}
      }}>{tab.label}</button>)}
  </div>;
}
