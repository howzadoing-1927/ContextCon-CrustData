"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiResult } from "@/lib/api/client";

export interface Resource<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  /** Wall-clock time of the last successful response. */
  fetchedAt: number | null;
  correlationId: string | null;
  refresh: () => Promise<void>;
}

/**
 * Fetches once per `key`, and re-fetches every `pollMs` while the tab is visible.
 * A failed poll keeps the last good data so the screen doesn't blank during a blip.
 */
export function useResource<T>(
  key: string | null,
  fetcher: () => Promise<ApiResult<T>>,
  options: { pollMs?: number } = {},
): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(Boolean(key));
  const [fetchedAt, setFetchedAt] = useState<number | null>(null);
  const [correlationId, setCorrelationId] = useState<string | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const keyRef = useRef(key);
  keyRef.current = key;

  const run = useCallback(async () => {
    const requestKey = keyRef.current;
    if (!requestKey) return;
    try {
      const result = await fetcherRef.current();
      if (keyRef.current !== requestKey) return;
      setData(result.data);
      setCorrelationId(result.correlationId);
      setFetchedAt(Date.now());
      setError(null);
    } catch (cause) {
      if (keyRef.current !== requestKey) return;
      setError(cause);
    } finally {
      if (keyRef.current === requestKey) setLoading(false);
    }
  }, []);

  useEffect(() => {
    setData(null);
    setError(null);
    setFetchedAt(null);
    if (!key) {
      setLoading(false);
      return;
    }
    setLoading(true);
    void run();
  }, [key, run]);

  useEffect(() => {
    if (!key || !options.pollMs) return;
    let timer: ReturnType<typeof setInterval> | null = null;
    const start = () => {
      if (timer) return;
      timer = setInterval(() => void run(), options.pollMs);
    };
    const stop = () => {
      if (timer) clearInterval(timer);
      timer = null;
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void run();
        start();
      } else stop();
    };
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [key, options.pollMs, run]);

  return { data, error, loading, fetchedAt, correlationId, refresh: run };
}
