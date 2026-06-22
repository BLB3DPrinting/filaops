import { useState, useEffect, useCallback } from "react";
import { getVersionInfo, isVersionLessThan, formatVersion } from "../utils/version";

const GITHUB_API_URL = "https://api.github.com/repos/BLB3DPrinting/filaops/releases/latest";
const SESSION_STORAGE_KEY = "filaops_version_check";
const SESSION_STORAGE_TIMESTAMP = "filaops_version_check_timestamp";
const CHECK_INTERVAL_MS = 1000 * 60 * 60; // 1 hour

/**
 * Hook for checking if a newer version is available.
 *
 * Behaviour depends on the deployment shape (reported by the backend's
 * /system/version endpoint):
 *
 *   - docker / manual: polls GitHub Releases and reports `updateAvailable`
 *     so the UI can render the "new version available" banner + manual
 *     upgrade runbook.
 *   - tauri: skips the GitHub poll entirely. The Tauri shell has its own
 *     auto-updater wired against a signed `latest.json` channel — it is the
 *     source of truth for "is there a newer version?", and double-polling
 *     would create banner ghosts (the SPA would say "v4.0.1 available" while
 *     Tauri is already downloading it in the background). `installMethod` is
 *     still exposed so AdminSettings can render the appropriate copy.
 *
 * @returns {object} {
 *   currentVersion, latestVersion, installMethod, updateAvailable,
 *   loading, error, checkForUpdates,
 * }
 */
export function useVersionCheck() {
  const [currentVersion, setCurrentVersion] = useState(null);
  const [latestVersion, setLatestVersion] = useState(null);
  const [installMethod, setInstallMethod] = useState("docker");
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const checkForUpdates = useCallback(async (force = false) => {
    // Check if we've already checked in this session (unless forced)
    if (!force) {
      const cached = sessionStorage.getItem(SESSION_STORAGE_KEY);
      const timestamp = sessionStorage.getItem(SESSION_STORAGE_TIMESTAMP);

      if (cached && timestamp) {
        const timeSinceCheck = Date.now() - parseInt(timestamp, 10);
        if (timeSinceCheck < CHECK_INTERVAL_MS) {
          // Use cached result
          const cachedData = JSON.parse(cached);
          setCurrentVersion(cachedData.currentVersion ?? null);
          setLatestVersion(cachedData.latestVersion);
          setUpdateAvailable(cachedData.updateAvailable);
          setInstallMethod(cachedData.installMethod ?? "docker");
          return;
        }
      }
    }

    setLoading(true);
    setError(null);

    try {
      const info = await getVersionInfo();
      setCurrentVersion(info.version);
      setInstallMethod(info.install_method);

      // Tauri installs delegate update detection to the Tauri auto-updater.
      // We still cache install_method + current version so the Settings UI
      // can render correctly.
      if (info.install_method === "tauri") {
        sessionStorage.setItem(
          SESSION_STORAGE_KEY,
          JSON.stringify({
            currentVersion: info.version,
            installMethod: info.install_method,
            latestVersion: null,
            updateAvailable: false,
          }),
        );
        sessionStorage.setItem(SESSION_STORAGE_TIMESTAMP, Date.now().toString());
        return;
      }

      const response = await fetch(GITHUB_API_URL, {
        method: "GET",
        headers: {
          Accept: "application/vnd.github.v3+json",
        },
      });

      if (!response.ok) {
        throw new Error(`GitHub API returned ${response.status}`);
      }

      const data = await response.json();

      // Extract version from tag (e.g., "v1.6.0" -> "1.6.0")
      const latest = formatVersion(data.tag_name || "");

      setLatestVersion(latest);
      const hasUpdate = isVersionLessThan(info.version, latest);
      setUpdateAvailable(hasUpdate);

      // Cache the result
      sessionStorage.setItem(
        SESSION_STORAGE_KEY,
        JSON.stringify({
          currentVersion: info.version,
          installMethod: info.install_method,
          latestVersion: latest,
          updateAvailable: hasUpdate,
        }),
      );
      sessionStorage.setItem(SESSION_STORAGE_TIMESTAMP, Date.now().toString());
    } catch (err) {
      setError(err.message);
      // Don't show error to user - just fail silently
      console.warn("Failed to check for updates:", err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-check on mount (once per session)
  useEffect(() => {
    checkForUpdates(false);
  }, [checkForUpdates]);

  return {
    currentVersion,
    latestVersion,
    installMethod,
    updateAvailable,
    loading,
    error,
    checkForUpdates,
  };
}

