import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch({ policy = { mode: "basic", gate_close: false }, putOk = true } = {}) {
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
  // Dynamic import after the fetch mock + module reset, mirroring the
  // QualityDashboard test so useToast shares the post-reset Toast context.
  const { default: QualitySettingsSection } = await import("../QualitySettingsSection");
  const { ToastProvider } = await import("../../Toast");
  const utils = render(
    <ToastProvider>
      <QualitySettingsSection />
    </ToastProvider>,
  );
  return { ...utils, calls };
}

describe("QualitySettingsSection", () => {
  it("renders the three modes and reflects the current policy", async () => {
    await renderSection({ policy: { mode: "full", gate_close: true } });
    await waitFor(() => expect(screen.getByText("Full")).toBeTruthy());
    expect(screen.getByText("Off")).toBeTruthy();
    expect(screen.getByText("Basic")).toBeTruthy();
    // The current mode (full) is the selected radio.
    expect(screen.getByDisplayValue("full").checked).toBe(true);
    expect(screen.getByDisplayValue("basic").checked).toBe(false);
  });

  it("saves the selected mode via PUT /system/settings/quality_mode", async () => {
    const { calls } = await renderSection({ policy: { mode: "basic", gate_close: false } });
    await waitFor(() => screen.getByText("Full"));

    fireEvent.click(screen.getByDisplayValue("full"));
    fireEvent.click(screen.getByText(/Save Quality Settings/i));

    await waitFor(() => {
      const put = calls.find((c) => c.url.includes("/system/settings/quality_mode"));
      expect(put).toBeTruthy();
      expect(put.opts.method).toBe("PUT");
      expect(JSON.parse(put.opts.body).value).toBe("full");
    });
  });

  it("disables the gate toggle unless mode is full", async () => {
    await renderSection({ policy: { mode: "basic", gate_close: false } });
    await waitFor(() => screen.getByText("Full"));
    // gate-close checkbox is the only checkbox in the section
    const gate = screen.getByRole("checkbox");
    expect(gate.disabled).toBe(true);

    fireEvent.click(screen.getByDisplayValue("full"));
    expect(gate.disabled).toBe(false);
  });
});
