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
});
