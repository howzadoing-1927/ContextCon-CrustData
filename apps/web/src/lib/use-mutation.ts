"use client";

import { useCallback, useRef, useState } from "react";
import type { ApiResult } from "@/lib/api/client";
import { newIdempotencyKey } from "@/lib/api/client";

export interface Mutation<I, T> {
  run: (input: I) => Promise<T | null>;
  pending: boolean;
  error: unknown;
  reset: () => void;
}

/**
 * One logical user action = one Idempotency-Key. The key is reused when the same
 * action is retried after a failure, and replaced once it succeeds or is reset.
 */
export function useMutation<I, T>(
  scope: string,
  perform: (input: I, idempotencyKey: string) => Promise<ApiResult<T>>,
): Mutation<I, T> {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const keyRef = useRef<string | null>(null);
  const performRef = useRef(perform);
  performRef.current = perform;

  const run = useCallback(
    async (input: I) => {
      keyRef.current ??= newIdempotencyKey(scope);
      setPending(true);
      setError(null);
      try {
        const result = await performRef.current(input, keyRef.current);
        keyRef.current = null;
        return result.data;
      } catch (cause) {
        setError(cause);
        return null;
      } finally {
        setPending(false);
      }
    },
    [scope],
  );

  const reset = useCallback(() => {
    keyRef.current = null;
    setError(null);
  }, []);

  return { run, pending, error, reset };
}
