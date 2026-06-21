import { useCallback, useEffect, useRef, useState } from "react";

/**
 * useApi(fetcher, deps) — runs `fetcher()` on mount / when deps change,
 * tracks {data, loading, error}, and exposes `refetch()` for manual reruns
 * (e.g. a "Retry" button or the historical-replay poll loop).
 */
export function useApi(fetcher, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetcherRef
      .current()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => run(), deps); // eslint-disable-line react-hooks/exhaustive-deps

  return { data, loading, error, refetch: run };
}
