/**
 * Listens for 'api:error' and shows a toast. Central place -> fewer silent failures.
 * Also detects tier limit errors and emits 'tier:limit-reached' event.
 */
import { useEffect, useRef } from "react";
import { on, emit } from "../lib/events";
import { useToast } from "./Toast";

/**
 * Maps technical error status codes and messages to user-friendly text.
 * Falls back to the original message if no mapping matches.
 */
function getFriendlyMessage(status, message) {
  // Status-code based mappings (checked first for precision)
  if (status === 401) {
    return "Your session has expired. Please log in again.";
  }
  if (status === 403) {
    return "You don't have permission to perform this action.";
  }
  if (status === 404) {
    return "The requested resource was not found.";
  }
  if (status === 429) {
    return "Too many requests. Please wait a moment and try again.";
  }
  if (status >= 500 && status < 600) {
    return "Something went wrong on the server. Please try again.";
  }

  // Message-pattern based mappings (network-level errors have status 0)
  const lower = (message || "").toLowerCase();
  if (lower.includes("failed to fetch") || lower.includes("networkerror") || lower.includes("network error")) {
    return "Unable to connect to server. Please check your connection.";
  }

  // No mapping found -- return the original message as-is
  return message || "An unexpected error occurred.";
}

export default function ApiErrorToaster() {
  const toast = useToast();
  const serverDownShown = useRef(false);

  useEffect(() => {
    return on("api:error", (e) => {
      const _url = e?.url || "";  // Reserved for future logging
      const status = e?.status ?? "";
      const msg = e?.message || "Request failed";
      const detail = e?.detail;

      // Check if this is a tier limit error
      if (status === 403 && detail?.code === "TIER_LIMIT_EXCEEDED") {
        // Emit special event for upgrade modal
        emit("tier:limit-reached", {
          resource: detail.resource,
          limit: detail.limit,
          current: detail.current,
          tier: detail.tier,
          message: detail.message,
        });
        return; // Don't show regular toast for tier limits
      }

      // Handle server unavailable (502, 503, network errors) gracefully
      // Don't spam toasts - just redirect to login once
      if (status === 502 || status === 503 || status === 0 || msg.includes("Failed to fetch") || msg.includes("Network")) {
        if (!serverDownShown.current) {
          serverDownShown.current = true;
          toast.info("Unable to connect to server. Please check your connection.");
          // Redirect to login after a brief delay
          setTimeout(() => {
            if (window.location.pathname !== "/admin/login") {
              window.location.href = "/admin/login";
            }
            serverDownShown.current = false;
          }, 2000);
        }
        return;
      }

      toast.error(getFriendlyMessage(status, msg));
    });
  }, [toast]);
  return null;
}

