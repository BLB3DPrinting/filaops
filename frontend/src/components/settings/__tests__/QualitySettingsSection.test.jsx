import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch({ policy = { mode: "basic", gate_action: "warn" }, putOk = true } = {}) {
  const calls = [];
  global.fetch = vi.fn().mockImplementation(async (url, opts) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    calls.push({ url: urlStr, opts });
    if (urlStr.includes("/quality/policy")) {
      return { ok: true, status: 200, json: async () => policy, text: async () => JSON.stringify(policy) };
    }
    // PUT /system/settings/{key}
    return {
      ok: putOk,
      status: putOk ? 200 : 400,
      json: async () => ({ detail: "rejected" }),
      text: async () => "",
    };
  });
  return calls;
}

async function renderSection(opts) {
  const calls = mockFetch(opts);
  const { default: QualitySettingsSection } = await import("../QualitySettingsSection");
  const { ToastProvider } = await import("../../Toast");
  const utils = render(
    <ToastProvider>
      <QualitySettingsSection />
    </ToastProvider>,
  );
  return { ...utils, calls };
}

const gateRadios = () => screen.getAllByRole("radio").filter((r) => r.name === "quality_gate_action");

describe("QualitySettingsSection", () => {
  it("renders the three modes and reflects the current policy", async () => {
    await renderSection({ policy: { mode: "full", gate_action: "block" } });
    await waitFor(() => expect(screen.getByText("Full")).toBeTruthy());

    const modeGroup = screen.getAllByRole("radio").filter((r) => r.name === "quality_mode");
    expect(modeGroup).toHaveLength(3);
    expect(modeGroup.find((r) => r.value === "full").checked).toBe(true);
    expect(modeGroup.find((r) => r.value === "basic").checked).toBe(false);
  });

  it("saves the selected mode via PUT /system/settings/quality_mode", async () => {
    const { calls } = await renderSection({ policy: { mode: "basic", gate_action: "warn" } });
    await waitFor(() => screen.getByText("Full"));

    const modeGroup = screen.getAllByRole("radio").filter((r) => r.name === "quality_mode");
    fireEvent.click(modeGroup.find((r) => r.value === "full"));
    fireEvent.click(screen.getByText(/Save Quality Settings/i));

    await waitFor(() => {
      const put = calls.find((c) => c.url.includes("/system/settings/quality_mode"));
      expect(put).toBeTruthy();
      expect(put.opts.method).toBe("PUT");
      expect(JSON.parse(put.opts.body).value).toBe("full");
    });
  });

  it("saves gate_action via PUT /system/settings/quality_gate_action", async () => {
    const { calls } = await renderSection({ policy: { mode: "full", gate_action: "warn" } });
    await waitFor(() => screen.getByText("Block"));

    const gate = gateRadios();
    fireEvent.click(gate.find((r) => r.value === "block"));
    fireEvent.click(screen.getByText(/Save Quality Settings/i));

    await waitFor(() => {
      const put = calls.find((c) => c.url.includes("/system/settings/quality_gate_action"));
      expect(put).toBeTruthy();
      expect(put.opts.method).toBe("PUT");
      expect(JSON.parse(put.opts.body).value).toBe("block");
    });
  });

  it("disables the gate selector unless mode is full", async () => {
    await renderSection({ policy: { mode: "basic", gate_action: "warn" } });
    await waitFor(() => screen.getByText("Full"));

    gateRadios().forEach((r) => expect(r.disabled).toBe(true));

    const modeGroup = screen.getAllByRole("radio").filter((r) => r.name === "quality_mode");
    fireEvent.click(modeGroup.find((r) => r.value === "full"));
    gateRadios().forEach((r) => expect(r.disabled).toBe(false));
  });

  it("reflects gate_action from the policy response", async () => {
    await renderSection({ policy: { mode: "full", gate_action: "block" } });
    await waitFor(() => screen.getByText("Block"));

    const gate = gateRadios();
    expect(gate.find((r) => r.value === "block").checked).toBe(true);
    expect(gate.find((r) => r.value === "warn").checked).toBe(false);
    expect(gate.find((r) => r.value === "off").checked).toBe(false);
  });
});
