/**
 * Unit tests for ApiErrorToaster.
 *
 * Covers:
 *  - TIER_LIMIT_EXCEEDED 403 → emits tier:limit-reached + shows toast.info fallback
 *  - require_tier string 403 → shows PRO-feature toast.info
 *  - structured 403 with message → shows toast.error with that message
 *  - generic 403 → shows permission-denied toast
 *  - 401 → session-expired toast
 *  - 5xx → server-error toast
 */
import { render, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ── hoisted mocks (must be first) ───────────────────────────────────────────
const { mocks } = vi.hoisted(() => ({
  mocks: {
    toastError: vi.fn(),
    toastInfo: vi.fn(),
    toastSuccess: vi.fn(),
    toastWarning: vi.fn(),
    emitted: [],
  },
}));

vi.mock("../Toast", () => ({
  useToast: () => ({
    error: mocks.toastError,
    info: mocks.toastInfo,
    success: mocks.toastSuccess,
    warning: mocks.toastWarning,
  }),
}));

// Real event bus — we capture emits ourselves
vi.mock("../../lib/events", async (importOriginal) => {
  const real = await importOriginal();
  return {
    ...real,
    emit: vi.fn((...args) => {
      mocks.emitted.push(args);
      real.emit(...args);
    }),
  };
});

import { emit as mockEmit, emit } from "../../lib/events";
import ApiErrorToaster from "../ApiErrorToaster";

// Helper: fire an api:error event and flush effects
function fireApiError(payload) {
  act(() => {
    emit("api:error", payload);
  });
}

beforeEach(() => {
  mocks.toastError.mockReset();
  mocks.toastInfo.mockReset();
  mocks.toastSuccess.mockReset();
  mocks.toastWarning.mockReset();
  mocks.emitted.length = 0;
  mockEmit.mockClear();
});

describe("ApiErrorToaster", () => {
  it("renders nothing (returns null)", () => {
    const { container } = render(<ApiErrorToaster />);
    expect(container.firstChild).toBeNull();
  });

  describe("TIER_LIMIT_EXCEEDED 403", () => {
    it("emits tier:limit-reached with resource info", () => {
      render(<ApiErrorToaster />);
      fireApiError({
        status: 403,
        detail: {
          code: "TIER_LIMIT_EXCEEDED",
          resource: "users",
          limit: 3,
          current: 3,
          tier: "community",
          message: "You've reached the user limit.",
        },
      });
      expect(mockEmit).toHaveBeenCalledWith("tier:limit-reached", {
        resource: "users",
        limit: 3,
        current: 3,
        tier: "community",
        message: "You've reached the user limit.",
      });
    });

    it("shows a toast.info fallback so something always appears", () => {
      render(<ApiErrorToaster />);
      fireApiError({
        status: 403,
        detail: {
          code: "TIER_LIMIT_EXCEEDED",
          resource: "printers",
          limit: 5,
          current: 5,
          tier: "community",
          message: "Printer limit reached.",
        },
      });
      expect(mocks.toastInfo).toHaveBeenCalledWith("Printer limit reached.");
    });

    it("uses generic fallback message when detail.message is absent", () => {
      render(<ApiErrorToaster />);
      fireApiError({
        status: 403,
        detail: {
          code: "TIER_LIMIT_EXCEEDED",
          resource: "users",
          limit: 3,
          current: 3,
          tier: "community",
        },
      });
      expect(mocks.toastInfo).toHaveBeenCalledWith(
        "You've reached a tier limit. Upgrade to PRO for more."
      );
    });

    it("does NOT call toast.error for tier-limit 403", () => {
      render(<ApiErrorToaster />);
      fireApiError({
        status: 403,
        detail: {
          code: "TIER_LIMIT_EXCEEDED",
          resource: "users",
          limit: 3,
          current: 3,
          tier: "community",
          message: "Limit hit.",
        },
      });
      expect(mocks.toastError).not.toHaveBeenCalled();
    });
  });

  describe("require_tier string 403 (PRO-feature gate)", () => {
    it("shows PRO-feature toast.info for 'requires Professional tier' message", () => {
      render(<ApiErrorToaster />);
      fireApiError({
        status: 403,
        detail: "This feature requires Professional tier or higher",
      });
      expect(mocks.toastInfo).toHaveBeenCalledWith(
        "This is a PRO feature — view upgrade options at Settings → License."
      );
    });

    it("matches case-insensitively on the word 'requires'", () => {
      render(<ApiErrorToaster />);
      fireApiError({
        status: 403,
        detail: "REQUIRES enterprise tier",
      });
      expect(mocks.toastInfo).toHaveBeenCalledTimes(1);
    });

    it("does NOT emit tier:limit-reached for string 403", () => {
      render(<ApiErrorToaster />);
      fireApiError({
        status: 403,
        detail: "This feature requires Professional tier or higher",
      });
      // mockEmit is only called once (for api:error itself) — NOT for tier:limit-reached
      const tierEmits = mocks.emitted.filter(([ev]) => ev === "tier:limit-reached");
      expect(tierEmits).toHaveLength(0);
    });

    it("does NOT treat a generic string 403 as PRO-feature", () => {
      render(<ApiErrorToaster />);
      fireApiError({ status: 403, detail: "Admin access required" });
      expect(mocks.toastInfo).not.toHaveBeenCalled();
      // Falls through to generic permission toast
      expect(mocks.toastError).toHaveBeenCalledWith(
        "You don't have permission to perform this action."
      );
    });
  });

  describe("structured 403 with message (other PRO endpoints)", () => {
    it("shows toast.error with the detail.message", () => {
      render(<ApiErrorToaster />);
      fireApiError({
        status: 403,
        detail: { message: "Shopify integration not licensed" },
      });
      expect(mocks.toastError).toHaveBeenCalledWith(
        "Shopify integration not licensed"
      );
    });
  });

  describe("generic 403 (permission denied)", () => {
    it("shows the generic permission-denied message", () => {
      render(<ApiErrorToaster />);
      fireApiError({ status: 403, message: "Forbidden" });
      expect(mocks.toastError).toHaveBeenCalledWith(
        "You don't have permission to perform this action."
      );
    });
  });

  describe("401", () => {
    it("shows session-expired message", () => {
      render(<ApiErrorToaster />);
      fireApiError({ status: 401, message: "Unauthorized" });
      expect(mocks.toastError).toHaveBeenCalledWith(
        "Your session has expired. Please log in again."
      );
    });
  });

  describe("5xx", () => {
    it("shows server-error message for 500", () => {
      render(<ApiErrorToaster />);
      fireApiError({ status: 500, message: "Internal Server Error" });
      expect(mocks.toastError).toHaveBeenCalledWith(
        "Something went wrong on the server. Please try again."
      );
    });
  });
});
