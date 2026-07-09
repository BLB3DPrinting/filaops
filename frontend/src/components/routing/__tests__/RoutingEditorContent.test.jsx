/**
 * Integration test for RoutingEditorContent (#876 PR-4).
 *
 * Covers the end-to-end contract the design calls for: adding an operation
 * through the new type picker sends operation_type on create, and no
 * longer mints a placeholder OPn operation_code for a blank code.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import RoutingEditorContent from "../RoutingEditorContent";

const OPERATION_TYPES = [
  {
    id: 1,
    code: "FDM_PRINT",
    label: "FDM Print",
    description: "Materials count when the production order completes.",
    category: "print",
    sort_order: 10,
  },
  {
    id: 8,
    code: "PACK_SHIP",
    label: "Pack / Ship",
    description: "Materials count when the order ships.",
    category: "shipping",
    sort_order: 80,
  },
];

const WORK_CENTERS = [
  { id: 1, code: "FDM-1", name: "FDM Printer 1", total_rate_per_hour: "10" },
];

function jsonResponse(data, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => data,
  };
}

let capturedCreateBody = null;

beforeEach(() => {
  capturedCreateBody = null;
  globalThis.fetch = vi.fn().mockImplementation(async (url, options = {}) => {
    const urlStr = typeof url === "string" ? url : url.toString();

    if (urlStr.includes("/routings/product/")) {
      // No routing exists yet for this product — editor starts empty.
      return jsonResponse({ detail: "not found" }, false, 404);
    }
    if (urlStr.includes("/work-centers")) {
      return jsonResponse(WORK_CENTERS);
    }
    if (urlStr.includes("/operation-types")) {
      return jsonResponse(OPERATION_TYPES);
    }
    if (urlStr.includes("/routings?templates_only=true")) {
      return jsonResponse([]);
    }
    if (urlStr.includes("/routings/") && options.method === "POST") {
      capturedCreateBody = JSON.parse(options.body);
      return jsonResponse({ id: 99, operations: [] });
    }
    return jsonResponse({});
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("RoutingEditorContent — operation type on create", () => {
  it("sends operation_type and does not mint an OPn operation_code", async () => {
    const onSuccess = vi.fn();
    render(
      <RoutingEditorContent
        productId={5}
        isActive={true}
        embedded={true}
        onSuccess={onSuccess}
        onCancel={vi.fn()}
      />
    );

    // Wait for the catalog fetches to resolve before opening the form.
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    fireEvent.click(await screen.findByText("+ Add Operation"));

    // The <select>s only accept a value once their matching <option> has
    // rendered (native select semantics) — wait for both fetched catalogs.
    await screen.findByRole("option", { name: "FDM Print" });
    await screen.findByRole("option", { name: "FDM-1 - FDM Printer 1" });

    fireEvent.change(screen.getByLabelText(/Operation Type/), {
      target: { value: "FDM_PRINT" },
    });
    fireEvent.change(screen.getByLabelText(/Work Center/), {
      target: { value: "1" },
    });
    // Deliberately leave the (now-secondary) operation code untouched.
    fireEvent.click(screen.getByText("Add"));

    fireEvent.click(screen.getByText("Create Routing"));

    await waitFor(() => expect(capturedCreateBody).not.toBeNull());
    expect(capturedCreateBody.operations).toHaveLength(1);
    const op = capturedCreateBody.operations[0];
    expect(op.operation_type).toBe("FDM_PRINT");
    // The old behavior minted `OP${idx + 1}` here — assert that's gone.
    expect(op.operation_code).not.toMatch(/^OP\d+$/);
    expect(op.operation_code).toBe("PRINT"); // canonical code for FDM_PRINT
  });

  it("blocks adding an operation with no type selected", async () => {
    render(
      <RoutingEditorContent
        productId={5}
        isActive={true}
        embedded={true}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    fireEvent.click(await screen.findByText("+ Add Operation"));

    await screen.findByRole("option", { name: "FDM-1 - FDM Printer 1" });
    fireEvent.change(screen.getByLabelText(/Work Center/), {
      target: { value: "1" },
    });
    expect(screen.getByText("Add")).toBeDisabled();
  });
});
