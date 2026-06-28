import { useEffect, useRef, useState, useCallback } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number = 3000
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const mounted = useRef(true);

  const poll = useCallback(() => {
    fetcher()
      .then((result) => {
        if (mounted.current) {
          setData(result);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (mounted.current) {
          setError(err instanceof Error ? err.message : "Polling failed");
          setLoading(false);
        }
      });
  }, [fetcher]);

  useEffect(() => {
    mounted.current = true;
    poll();
    timer.current = setInterval(poll, intervalMs);
    return () => {
      mounted.current = false;
      if (timer.current) clearInterval(timer.current);
    };
  }, [poll, intervalMs]);

  return { data, error, loading };
}
