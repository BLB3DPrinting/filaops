/**
 * Listens for 'api:error' and shows a toast. Central place -> fewer silent failures.
 * Also detects tier limit errors and emits 'tier:limit-reached' event.
 *
 * 403 handling matrix:
 *  - detail.code === "TIER_LIMIT_EXCEEDED" → emit tier:limit-reached (opens UpgradeModal)
 *    + show toast.info fallback so something always appears if the modal listener fails.
 *  - detail (string) contains "require"/"requires" (require_tier decorator) → PRO-feature
 *    toast with link to /admin/license.
 *  - detail.message present → show detail.message directly.
 *  - anything else → generic "no permission" text.
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

      // Tier-limit 403: open upgrade modal AND show a fallback toast so
      // something is always visible even if UpgradeModal is not mounted.
      if (status === 403 && detail && typeof detail === "object" && detail.code === "TIER_LIMIT_EXCEEDED") {
        emit("tier:limit-reached", {
          resource: detail.resource,
          limit: detail.limit,
          current: detail.current,
          tier: detail.tier,
          message: detail.message,
        });
        toast.info(detail.message || "You've reached a tier limit. Upgrade to PRO for more.");
        return;
      }

      // PRO-feature 403: backend's require_tier decorator sends a plain string
      // like "This feature requires Professional tier or higher".  Show an
      // actionable message linking straight to the License page.
      // Guard: require both "require"/"requires" AND a whole-word tier/plan keyword so
      // strings like "Admin approval requires manager role" are not misclassified
      // ("approval" contains "pro" as a substring — use \b word boundaries).
      // \brequires?\b matches "require" and "requires" but NOT "required" (word boundary
      // fails before the trailing 'd').
      if (status === 403 && typeof detail === "string") {
        const isTierRequirement =
          /\brequires?\b/i.test(detail) &&
          /\b(tier|professional|enterprise|pro)\b/i.test(detail);
        if (isTierRequirement) {
          toast.info("This is a PRO feature — view upgrade options at Settings → License.");
          return;
        }
      }

      // Structured 403 with a message field (other PRO-endpoint errors)
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
