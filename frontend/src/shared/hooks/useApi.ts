import { useCallback, useEffect, useReducer, useRef } from "react";

type State<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; error: string };

type Action<T> =
  | { type: "start" }
  | { type: "done"; data: T }
  | { type: "fail"; error: string };

function reducer<T>(_state: State<T>, action: Action<T>): State<T> {
  switch (action.type) {
    case "start":
      return { status: "loading" };
    case "done":
      return { status: "ready", data: action.data };
    case "fail":
      return { status: "error", error: action.error };
  }
}

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = []
) {
  const [state, dispatch] = useReducer(reducer<T>, { status: "idle" });
  const cancelled = useRef(false);

  const execute = useCallback(() => {
    dispatch({ type: "start" });
    fetcher()
      .then((data) => {
        if (!cancelled.current) dispatch({ type: "done", data });
      })
      .catch((err: unknown) => {
        if (!cancelled.current) {
          dispatch({
            type: "fail",
            error: err instanceof Error ? err.message : "Unknown error",
          });
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    cancelled.current = false;
    execute();
    return () => {
      cancelled.current = true;
    };
  }, [execute]);

  return { ...state, refetch: execute };
}
