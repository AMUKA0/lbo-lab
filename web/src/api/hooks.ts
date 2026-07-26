/**
 * Data-fetching hooks.
 *
 * Three properties matter here and each is deliberate:
 *
 * - **Debounced.** Sliders fire continuously; the engine is fast but the network
 *   round trip is not free. Assumptions settle for a beat before we ask.
 * - **Abortable.** The previous request is cancelled when a new one starts, so a
 *   slow response can never overwrite a newer one.
 * - **Stale-while-loading.** The last good data stays on screen while the next
 *   arrives, so charts fade rather than collapsing to empty frames on every
 *   keystroke. `loading` drives a subtle opacity shift, not a spinner takeover.
 */

import { useEffect, useRef, useState } from "react";

import { StructureFailure } from "./client";

export function useDebounced<T>(value: T, delayMs = 220): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return settled;
}

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** True when the engine rejected the structure, as opposed to a transport fault. */
  structureFailed: boolean;
}

/**
 * Run `fetcher` whenever `input` changes.
 *
 * `enabled` lets a tab opt out of computing until it is actually visible — the
 * sensitivity grid is ~25 engine runs and there is no reason to pay for it
 * while the user is reading the debt schedule.
 */
export function useEngineQuery<TInput, TResult>(
  input: TInput,
  fetcher: (input: TInput, signal: AbortSignal) => Promise<TResult>,
  enabled = true,
): AsyncState<TResult> {
  const [state, setState] = useState<AsyncState<TResult>>({
    data: null,
    loading: enabled,
    error: null,
    structureFailed: false,
  });
  // `fetcher` is usually an inline arrow; keeping it in a ref stops it from
  // retriggering the effect on every render.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    setState((prev) => ({ ...prev, loading: true }));

    fetcherRef
      .current(input, controller.signal)
      .then((data) =>
        setState({ data, loading: false, error: null, structureFailed: false }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return; // superseded, not failed
        setState({
          data: null,
          loading: false,
          error: error instanceof Error ? error.message : "Something went wrong.",
          structureFailed: error instanceof StructureFailure,
        });
      });

    return () => controller.abort();
  }, [input, enabled]);

  return state;
}
