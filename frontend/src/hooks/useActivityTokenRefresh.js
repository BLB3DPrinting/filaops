/**
 * Activity-Based Token Refresh Hook
 *
 * Prevents users from losing work due to session expiration while actively working.
 * Tracks user activity and calls POST /auth/refresh periodically.
 *
 * With httpOnly cookies the JS layer cannot read token expiry, so we refresh
 * on a fixed interval while the user is active.
 */
import { useEffect, useRef, useCallback } from "react";
import { API_URL } from "../config/api";

// How often to attempt a refresh (in ms)
const REFRESH_INTERVAL = 10 * 60 * 1000; // 10 minutes

// Consider user inactive after this many minutes of no activity
const INACTIVITY_TIMEOUT_MINUTES = 25;

/**
 * Hook to automatically refresh auth tokens based on user activity.
 *
 * Usage:
 *   useActivityTokenRefresh(); // Call once in your app root or layout
 */
export default function useActivityTokenRefresh() {
  const lastActivityRef = useRef(Date.now());
  const isRefreshingRef = useRef(false);

  // Update last activity timestamp on user interaction
  const updateActivity = useCallback(() => {
    lastActivityRef.current = Date.now();
  }, []);

  // Refresh the access token by calling POST /auth/refresh (cookie-based)
  const refreshToken = useCallback(async () => {
    if (isRefreshingRef.current) return false;
    isRefreshingRef.current = true;

    try {
      const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        // Refresh failed — session expired, user needs to log in again
        console.warn("Token refresh failed — session may have expired");
        return false;
      }

      console.debug("Token refreshed successfully");
      return true;
    } catch (error) {
      console.error("Token refresh error:", error);
      return false;
    } finally {
      isRefreshingRef.current = false;
    }
  }, []);

  // Check if user is active, then refresh
  const checkAndRefresh = useCallback(() => {
    // Only refresh if we appear to be logged in (adminUser in localStorage)
    if (!localStorage.getItem("adminUser")) return;

    const now = Date.now();
    const inactivityMs = INACTIVITY_TIMEOUT_MINUTES * 60 * 1000;
    const timeSinceActivity = now - lastActivityRef.current;
    const isUserActive = timeSinceActivity < inactivityMs;

    if (isUserActive) {
      console.debug("User active — refreshing token");
      refreshToken();
    }
  }, [refreshToken]);

  useEffect(() => {
    // Activity event listeners
    const events = ["mousedown", "keydown", "mousemove", "scroll", "touchstart"];

    // Throttle activity updates to avoid excessive calls
    let activityTimeout = null;
    const throttledActivity = () => {
      if (!activityTimeout) {
        updateActivity();
        activityTimeout = setTimeout(() => {
          activityTimeout = null;
        }, 5000); // Only update once every 5 seconds max
      }
    };

    // Add event listeners
    events.forEach(event => {
      window.addEventListener(event, throttledActivity, { passive: true });
    });

    // Set up periodic token refresh
    const intervalId = setInterval(checkAndRefresh, REFRESH_INTERVAL);

    // Cleanup
    return () => {
      events.forEach(event => {
        window.removeEventListener(event, throttledActivity);
      });
      clearInterval(intervalId);
      if (activityTimeout) clearTimeout(activityTimeout);
    };
  }, [updateActivity, checkAndRefresh]);
}
