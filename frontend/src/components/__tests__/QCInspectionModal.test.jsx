import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
});

const PO = {
  id: 7,
  code: "PO-007",
  product_name: "Widget",
  quantity_completed: 5,
  status: "complete",
};

const jsonRes = (data) => ({ ok: true, status: 200, json: async () => data });

function mockFetch({
  details = [{ id: 3, code: "warp", name: "Warping", severity: "major" }],
  operations = [{ id: 11, sequence: 10, operation_name: "Final QC", operation_code: "QC" }],
  postOk = true,
  inspectionId = null,
} = {}) {
  const calls = [];
  global.fetch = vi.fn().mockImplementation(async (url, opts) => {
    const u = typeof url === "string" ? url : url.toString();
    calls.push({ url: u, opts });
    if (u.includes("/defect-reasons")) return jsonRes({ reasons: details.map((d) => d.code), details });
    if (/\/production-orders\/\d+$/.test(u)) return jsonRes({ operations });
    if (u.includes("/photos")) return jsonRes([]); // QCInspectionPhotos list (photos step)
    if (u.endsWith("/qc")) return { ok: postOk, status: postOk ? 200 : 400, json: async () => ({ message: "ok", inspection_id: inspectionId, detail: "err" }) };
    return jsonRes({});
  });
  return calls;
}

async function renderModal(opts) {
  const calls = mockFetch(opts);
  const { default: QCInspectionModal } = await import("../QCInspectionModal");
  const { ToastProvider } = await import("../Toast");
  const onComplete = vi.fn();
  const utils = render(
    <ToastProvider>
      <QCInspectionModal productionOrder={PO} onClose={() => {}} onComplete={onComplete} />
    </ToastProvider>,
  );
  return { ...utils, calls, onComplete };
}

describe("QCInspectionModal", () => {
  it("renders the four result options", async () => {
    await renderModal();
    expect(screen.getByText("Pass")).toBeTruthy();
    expect(screen.getByText("Fail")).toBeTruthy();
    expect(screen.getByText("Waive")).toBeTruthy();
    expect(screen.getByText("Conditional")).toBeTruthy();
  });

  it("reveals defect reasons only when not a clean pass", async () => {
    await renderModal();
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2)); // reasons + order fetched
    expect(screen.queryByText(/Warping/)).toBeNull(); // hidden while Pass is selected
    fireEvent.click(screen.getByText("Fail"));
    await waitFor(() => expect(screen.getByText(/Warping/)).toBeTruthy()); // option now shown
  });

  it("renders the operation selector from the fetched order", async () => {
    await renderModal();
    await waitFor(() => expect(screen.getByText(/Operation inspected/)).toBeTruthy());
    expect(screen.getByText(/#10 Final QC/)).toBeTruthy();
  });

  it("does not submit a defect reason after switching back to Pass", async () => {
    const { calls } = await renderModal();
    fireEvent.click(screen.getByText("Fail"));
    await waitFor(() => screen.getByText(/Warping/));
    const defectSelect = screen
      .getAllByRole("combobox")
      .find((s) => s.textContent.includes("Warping"));
    fireEvent.change(defectSelect, { target: { value: "3" } }); // pick a defect
    expect(defectSelect.value).toBe("3"); // ...the pick actually stuck
    fireEvent.click(screen.getByText("Pass")); // ...then go back to a clean pass
    fireEvent.click(screen.getByText(/Record Pass/));

    await waitFor(() => {
      const post = calls.find((c) => c.url.endsWith("/qc"));
      expect(post).toBeTruthy();
      const body = JSON.parse(post.opts.body);
      expect(body.result).toBe("passed");
      expect(body.defect_reason_id).toBeNull(); // stale pick not submitted
    });
  });

  it("blocks submit when a measurement row has data but no characteristic", async () => {
    const { calls } = await renderModal();
    fireEvent.click(screen.getByText(/Add measurement/));
    fireEvent.change(screen.getByPlaceholderText("Measured"), { target: { value: "10.1" } });
    // no characteristic entered
    fireEvent.click(screen.getByText(/Record Pass/));
    await waitFor(() => expect(screen.getByText(/Add a characteristic/i)).toBeTruthy());
    expect(calls.some((c) => c.url.endsWith("/qc"))).toBe(false); // POST never fired
  });

  it("submits the selected result + captured measurement in one POST", async () => {
    const { calls, onComplete } = await renderModal();
    fireEvent.click(screen.getByText(/Add measurement/));
    fireEvent.change(screen.getByPlaceholderText("Characteristic"), { target: { value: "bore" } });
    fireEvent.change(screen.getByPlaceholderText("Measured"), { target: { value: "10.1" } });
    fireEvent.click(screen.getByText(/Record Pass/));

    await waitFor(() => {
      const post = calls.find((c) => c.url.endsWith("/qc"));
      expect(post).toBeTruthy();
      const body = JSON.parse(post.opts.body);
      expect(body.result).toBe("passed");
      expect(body.measurements).toHaveLength(1);
      expect(body.measurements[0].characteristic).toBe("bore");
      expect(body.measurements[0].measured_value).toBe(10.1);
    });
    await waitFor(() => expect(onComplete).toHaveBeenCalled());
  });

  it("advances to the optional photos step after recording, then finishes on Done", async () => {
    const { onComplete } = await renderModal({ inspectionId: 42 });
    fireEvent.click(screen.getByText(/Record Pass/));
    await waitFor(() => expect(screen.getByText(/attach photos/i)).toBeTruthy());
    expect(onComplete).not.toHaveBeenCalled(); // not until the user is done
    fireEvent.click(screen.getByText("Done"));
    expect(onComplete).toHaveBeenCalled();
  });
});
