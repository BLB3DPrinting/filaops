import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { slugifyCode } from "../qualityPlanEditor.utils";

// useApi is mocked so we can assert the exact payload posted.
const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() },
}));
vi.mock("../../hooks/useApi", () => ({ useApi: () => api }));

import QualityPlanEditor from "../QualityPlanEditor";
import { ToastProvider } from "../Toast";

function renderEditor(props = {}) {
  const onSaved = vi.fn();
  const utils = render(
    <ToastProvider>
      <QualityPlanEditor
        plan={null}
        onClose={() => {}}
        onSaved={onSaved}
        {...props}
      />
    </ToastProvider>
  );
  return { ...utils, onSaved };
}

beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  api.patch.mockReset();
  api.del.mockReset();
  api.get.mockResolvedValue({ items: [] });
  api.post.mockResolvedValue({ id: 1 });
  api.patch.mockResolvedValue({ id: 1 });
});

describe("slugifyCode", () => {
  it("derives a stable, uppercase, underscore-joined code", () => {
    expect(slugifyCode("Bore diameter (mm)")).toBe("BORE_DIAMETER_MM");
    expect(slugifyCode("  Surface finish  ")).toBe("SURFACE_FINISH");
    expect(slugifyCode("")).toBe("");
  });
});

describe("QualityPlanEditor", () => {
  it("toggling template hides the product picker", () => {
    renderEditor();
    expect(screen.getByLabelText("Product")).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/Reusable template/));
    expect(screen.queryByLabelText("Product")).toBeNull();
  });

  it("auto-derives the characteristic code from its name on blur", () => {
    renderEditor();
    const nameInput = screen.getByLabelText("Characteristic name");
    fireEvent.change(nameInput, { target: { value: "Bore diameter" } });
    fireEvent.blur(nameInput);
    expect(screen.getByLabelText("Characteristic code").value).toBe(
      "BORE_DIAMETER"
    );
  });

  it("does not clobber a manually entered code", () => {
    renderEditor();
    const codeInput = screen.getByLabelText("Characteristic code");
    fireEvent.change(codeInput, { target: { value: "CUSTOM" } });
    const nameInput = screen.getByLabelText("Characteristic name");
    fireEvent.change(nameInput, { target: { value: "Bore diameter" } });
    fireEvent.blur(nameInput);
    expect(screen.getByLabelText("Characteristic code").value).toBe("CUSTOM");
  });

  it("blocks save when a lower limit exceeds the upper limit", async () => {
    renderEditor();
    fireEvent.click(screen.getByLabelText(/Reusable template/));
    fireEvent.change(screen.getByLabelText(/Plan code/), {
      target: { value: "QP-T" },
    });
    fireEvent.change(screen.getByLabelText(/Plan name/), {
      target: { value: "Template" },
    });
    fireEvent.change(screen.getByLabelText("Characteristic name"), {
      target: { value: "bore" },
    });
    fireEvent.change(screen.getByLabelText("Lower spec limit"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("Upper spec limit"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByText("Create plan"));
    await waitFor(() =>
      expect(screen.getByText(/lower limit cannot exceed/i)).toBeTruthy()
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it("posts a template plan with a normalized characteristic payload", async () => {
    renderEditor();
    fireEvent.click(screen.getByLabelText(/Reusable template/));
    fireEvent.change(screen.getByLabelText(/Plan code/), {
      target: { value: "QP-T1" },
    });
    fireEvent.change(screen.getByLabelText(/Plan name/), {
      target: { value: "Template plan" },
    });
    const nameInput = screen.getByLabelText("Characteristic name");
    fireEvent.change(nameInput, { target: { value: "Bore diameter" } });
    fireEvent.blur(nameInput);
    fireEvent.change(screen.getByLabelText("Upper spec limit"), {
      target: { value: "10.1" },
    });
    fireEvent.click(screen.getByText("Create plan"));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [url, payload] = api.post.mock.calls[0];
    expect(url).toContain("/quality-plans");
    expect(payload.is_template).toBe(true);
    expect(payload.product_id).toBeNull();
    expect(payload.characteristics).toHaveLength(1);
    expect(payload.characteristics[0]).toMatchObject({
      code: "BORE_DIAMETER",
      characteristic: "Bore diameter",
      upper_limit: "10.1",
      sequence: 0,
    });
  });

  it("rejects an empty version instead of silently coercing it to 1", async () => {
    renderEditor();
    fireEvent.click(screen.getByLabelText(/Reusable template/));
    fireEvent.change(screen.getByLabelText(/Plan code/), {
      target: { value: "QP-V" },
    });
    fireEvent.change(screen.getByLabelText(/Plan name/), {
      target: { value: "V" },
    });
    fireEvent.change(screen.getByLabelText("Characteristic name"), {
      target: { value: "x" },
    });
    fireEvent.change(screen.getByLabelText(/Version/), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByText("Create plan"));
    await waitFor(() =>
      expect(
        screen.getByText(/Version must be a positive integer/i)
      ).toBeTruthy()
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it("lets the user pick a product from keyboard-focusable search results", async () => {
    api.get.mockResolvedValue({
      items: [{ id: 5, sku: "WID-1", name: "Widget" }],
    });
    renderEditor();
    fireEvent.change(screen.getByLabelText("Product"), {
      target: { value: "wid" },
    });
    // Results render as <button>s (not a multi-row select), so each option is
    // individually focusable/activatable — no arrow-key auto-commit trap.
    const option = await screen.findByRole("button", { name: /WID-1/ });
    fireEvent.click(option);
    expect(screen.getByText(/Selected:/)).toBeTruthy();
    expect(screen.getByText(/WID-1 — Widget/)).toBeTruthy();
  });

  it("swaps spec-limit inputs for an acceptance-criteria field on attribute type", () => {
    renderEditor();
    expect(screen.getByLabelText("Nominal")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Characteristic type"), {
      target: { value: "attribute" },
    });
    expect(screen.queryByLabelText("Nominal")).toBeNull();
    expect(screen.queryByLabelText("Lower spec limit")).toBeNull();
    expect(screen.getByLabelText("Acceptance criteria")).toBeTruthy();
  });

  it("posts an attribute characteristic with null limits + acceptance criteria", async () => {
    renderEditor();
    fireEvent.click(screen.getByLabelText(/Reusable template/));
    fireEvent.change(screen.getByLabelText(/Plan code/), {
      target: { value: "QP-A" },
    });
    fireEvent.change(screen.getByLabelText(/Plan name/), {
      target: { value: "Attr plan" },
    });
    fireEvent.change(screen.getByLabelText("Characteristic name"), {
      target: { value: "Surface defects" },
    });
    fireEvent.change(screen.getByLabelText("Characteristic type"), {
      target: { value: "attribute" },
    });
    fireEvent.change(screen.getByLabelText("Acceptance criteria"), {
      target: { value: "No visible defects" },
    });
    fireEvent.click(screen.getByText("Create plan"));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const payload = api.post.mock.calls[0][1];
    expect(payload.characteristics[0]).toMatchObject({
      characteristic: "Surface defects",
      characteristic_type: "attribute",
      acceptance_criteria: "No visible defects",
      nominal: null,
      lower_limit: null,
      upper_limit: null,
      unit: null,
    });
  });
});
