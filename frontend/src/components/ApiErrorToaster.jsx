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
      const url = e?.url || "";
      const status = e?.status ?? "";
      const msg = e?.message || "Request failed";
      const detail = e?.detail;
      const isRecoverableIntegrationError =
        url.includes("/api/v1/pro/integrations/bambuddy") ||
        url.includes("/api/v1/pro/printer-providers/bambuddy");

      // Check if this is a tier limit error
      if (status === 403 && detail && typeof detail === "object" && detail.code === "TIER_LIMIT_EXCEEDED") {
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

      // PRO feature endpoint returned 403 — show contextual message
      if (status === 403 && detail && typeof detail === "object" && detail.message) {
        toast.error(detail.message);
        return;
      }

      // Handle server unavailable (502, 503, network errors) gracefully.
      // Bambuddy failures are recoverable integration errors; core API outages
      // block the page and should return users to the login/start point.
      if (status === 502 || status === 503 || status === 0 || msg.includes("Failed to fetch") || msg.includes("Network")) {
        if (!serverDownShown.current) {
          serverDownShown.current = true;
          if (isRecoverableIntegrationError) {
            toast.info("Unable to connect to Bambuddy. FilaOps is still available.");
          } else {
            toast.info("Unable to connect to FilaOps. Returning to login...");
            setTimeout(() => {
              if (!window.location.pathname.includes("/admin/login")) {
                window.location.href = "/admin/login";
              }
            }, 3000);
          }
          setTimeout(() => {
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
