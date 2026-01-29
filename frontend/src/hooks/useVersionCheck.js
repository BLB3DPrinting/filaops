import { useState, useEffect, useCallback } from "react";
import { getCurrentVersion, isVersionLessThan, formatVersion } from "../utils/version";

const GITHUB_API_URL = "https://api.github.com/repos/Blb3D/filaops/releases/latest";
const SESSION_STORAGE_KEY = "filaops_version_check";
const SESSION_STORAGE_TIMESTAMP = "filaops_version_check_timestamp";
const CHECK_INTERVAL_MS = 1000 * 60 * 60; // 1 hour

/**
 * Hook for checking if a newer version is available
 * @returns {object} { latestVersion, updateAvailable, loading, error, checkForUpdates }
 */
export function useVersionCheck() {
  const [latestVersion, setLatestVersion] = useState(null);
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
          setLatestVersion(cachedData.latestVersion);
          setUpdateAvailable(cachedData.updateAvailable);
          return;
        }
      }
    }

    setLoading(true);
    setError(null);

    try {
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
      const current = await getCurrentVersion();

      setLatestVersion(latest);
      const hasUpdate = isVersionLessThan(current, latest);
      setUpdateAvailable(hasUpdate);

      // Cache the result
      sessionStorage.setItem(
        SESSION_STORAGE_KEY,
        JSON.stringify({ latestVersion: latest, updateAvailable: hasUpdate })
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
    latestVersion,
    updateAvailable,
    loading,
    error,
    checkForUpdates,
  };
}

