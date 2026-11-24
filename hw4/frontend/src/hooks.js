/* Hooks shared by the pages */

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import { REFRESH_MS } from "./utils";

/**
 * Poll GET /api/lectures/{code}/ every few seconds (the lecture with its topics and
 * questions). Returns { lecture, error, status, refresh }. `refresh()` re-fetches now —
 * pages call it after an action so the change shows immediately.
 */
export function useLecturePolling(code, intervalMs = REFRESH_MS) {
  const [lecture, setLecture] = useState(null);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState("Loading…");
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api(`/api/lectures/${code}/`);
      if (!alive.current) return;
      setLecture(data);
      setError(null);
      setStatus(`Updated ${new Date().toLocaleTimeString()} · refreshes every ${intervalMs / 1000}s`);
    } catch (e) {
      if (!alive.current) return;
      setError(e);
      setStatus(e.status === 404 ? "Lecture not found" : `Cannot reach the API: ${e.message}`);
    }
  }, [code, intervalMs]);

  useEffect(() => {
    alive.current = true;
    refresh();
    const timer = setInterval(refresh, intervalMs);
    return () => { alive.current = false; clearInterval(timer); };
  }, [refresh, intervalMs]);

  return { lecture, error, status, refresh };
}

/** Debounced value: the returned value changes `ms` after the input stops changing. */
export function useDebounced(value, ms = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

/** Page title */
export function useTitle(title) {
  useEffect(() => {
    const previous = document.title;
    document.title = title ? `${title} · Raise Hand` : "Raise Hand";
    return () => { document.title = previous; };
  }, [title]);
}
