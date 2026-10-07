import { useCallback, useContext, useEffect, useRef } from "react";
import { UNSAFE_DataRouterContext, useBlocker } from "react-router-dom";
import { Sheet } from "./Sheet";

type Props = { when: boolean; queryKeys?: string[] };

export function UnsavedChangesGuard({ when, queryKeys = [] }: Props) {
  const router = useContext(UNSAFE_DataRouterContext);
  useEffect(() => {
    if (!when) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [when]);
  return router ? <RouterGuard when={when} queryKeys={queryKeys} /> : null;
}

function RouterGuard({ when, queryKeys = [] }: Props) {
  const current = useRef({ when, queryKeys });
  current.current = { when, queryKeys };
  const shouldBlock = useCallback(({ currentLocation, nextLocation }: {
    currentLocation: { pathname: string; search: string }; nextLocation: { pathname: string; search: string };
  }) => current.current.when && (
    currentLocation.pathname !== nextLocation.pathname || current.current.queryKeys.some(key =>
      new URLSearchParams(currentLocation.search).get(key) !== new URLSearchParams(nextLocation.search).get(key))
  ), []);
  const blocker = useBlocker(shouldBlock);
  useEffect(() => { if (!when && blocker.state === "blocked") blocker.reset(); }, [when, blocker]);
  return <Sheet layer={300} open={blocker.state === "blocked"} onClose={() => blocker.state === "blocked" && blocker.reset()} title="离开前确认未保存内容">
    <p>此处还有未保存内容或正在上传的文件。离开将放弃当前编辑，并取消尚未完成的上传。</p>
    <div className="data-row-actions"><button className="btn btn-primary" onClick={() => blocker.state === "blocked" && blocker.reset()}>继续编辑</button>
      <button className="btn btn-danger" onClick={() => blocker.state === "blocked" && blocker.proceed()}>放弃并离开</button></div>
  </Sheet>;
}
