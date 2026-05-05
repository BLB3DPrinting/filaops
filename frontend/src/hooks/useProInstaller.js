/**
 * useProInstaller — drives the PRO wheel install flow from AdminLicense.
 *
 * Wraps the PR-04 backend endpoints:
 *   POST /api/v1/admin/system/pro/install        — schedules background install
 *   GET  /api/v1/admin/system/pro/install/status — polls progress
 *
 * Returns:
 *   installState — { state, progress, error, installed_version,
 *                    started_at, completed_at }
 *   startInstall() — POSTs and starts polling; safe to call from idle/error
 *   resetInstall() — local-only reset to idle (clears error UI for retry)
 *   isPolling      — true while a setInterval poll is active
 *
 * State machine mirrors the backend:
 *   idle -> downloading -> verifying -> installing -> restart_required
 *                                                  -> error (retryable)
 *
 * Polling cadence: every 2s while state is one of the in-progress values.
 * Stops automatically on terminal states (restart_required, error) and on
 * unmount. Auth is delegated to useApi (httpOnly cookie + credentials:
 * 'include'); the hook does not touch localStorage.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "./useApi";

const STATUS_URL = "/api/v1/admin/system/pro/install/status";
const INSTALL_URL = "/api/v1/admin/system/pro/install";
const POLL_INTERVAL_MS = 2000;
const IN_PROGRESS_STATES = new Set(["downloading", "verifying", "installing"]);

const INITIAL_STATE = Object.freeze({
  state: "idle",
  progress: "",
  error: null,
  installed_version: null,
  started_at: null,
  completed_at: null,
});

export function useProInstaller() {
  const api = useApi();

  const [installState, setInstallState] = useState(INITIAL_STATE);
  const [isPolling, setIsPolling] = useState(false);

  // setInterval handle. Held in a ref because the cleanup needs to read the
  // *current* timer regardless of which render scheduled it.
  const pollTimerRef = useRef(null);
  // Tracks whether the component is still mounted so async work doesn't
  // call setState after unmount (React will warn otherwise).
  const mountedRef = useRef(true);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setIsPolling(false);
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.get(STATUS_URL);
      if (!mountedRef.current) return null;
      setInstallState((prev) => ({ ...prev, ...data }));
      // Terminal state -> stop polling. The check happens here (not in an
      // effect) so the interval terminates the same tick the state lands.
      if (!IN_PROGRESS_STATES.has(data.state)) {
        stopPolling();
      }
      return data;
    } catch (err) {
      // A failed poll is non-fatal — the install pipeline lives server-side
      // and the next poll may succeed. We surface the error in installState
      // so the UI can show it without losing prior progress info.
      if (!mountedRef.current) return null;
      setInstallState((prev) => ({
        ...prev,
        error: err?.message || "Failed to fetch install status",
      }));
      return null;
    }
  }, [api, stopPolling]);

  const startPolling = useCallback(() => {
    if (pollTimerRef.current !== null) return; // already polling
    setIsPolling(true);
    pollTimerRef.current = setInterval(fetchStatus, POLL_INTERVAL_MS);
  }, [fetchStatus]);

  const startInstall = useCallback(async () => {
    // Optimistically reflect the trigger so the UI flips to a busy state
    // immediately, before the first poll lands.
    setInstallState((prev) => ({
      ...prev,
      state: "downloading",
      error: null,
      progress: "Starting install...",
    }));
    try {
      await api.post(INSTALL_URL, {});
      startPolling();
      // Kick an immediate poll so the UI surfaces real backend progress
      // ~instantly instead of waiting a full POLL_INTERVAL_MS.
      fetchStatus();
    } catch (err) {
      if (!mountedRef.current) return;
      // Trigger failed (400/409/500). Surface it in error state — same
      // shape as backend-pipeline failures so the UI has one error path.
      stopPolling();
      setInstallState((prev) => ({
        ...prev,
        state: "error",
        error: err?.message || "Failed to start install",
      }));
    }
  }, [api, fetchStatus, startPolling, stopPolling]);

  const resetInstall = useCallback(() => {
    stopPolling();
    setInstallState(INITIAL_STATE);
  }, [stopPolling]);

  // On mount: read the current backend state once so navigating to the page
  // mid-install reflects reality (e.g. a different admin tab triggered it,
  // or the user reloaded during downloading). If the state is in-progress,
  // resume polling automatically.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.get(STATUS_URL);
        if (cancelled || !mountedRef.current) return;
        setInstallState((prev) => ({ ...prev, ...data }));
        if (IN_PROGRESS_STATES.has(data.state)) {
          startPolling();
        }
      } catch {
        // Initial read failure is silent — the install button still works,
        // and a real attempt will surface a real error.
      }
    })();
    return () => {
      cancelled = true;
    };
    // Intentionally only on mount — re-running on api identity change would
    // re-poll on every render given useMemo's referential stability.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      mountedRef.current = false;
      if (pollTimerRef.current !== null) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

  return {
    installState,
    startInstall,
    resetInstall,
    isPolling,
  };
}
