import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { normalizeSerialPrefix } from "../serialPrefix";

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch({ prefix = "SN-", patch } = {}) {
  const calls = [];
  global.fetch = vi.fn().mockImplementation(async (url, opts = {}) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    calls.push({ url: urlStr, opts });
    if (opts.method === "PATCH") {
      const sent = JSON.parse(opts.body).serial_number_prefix;
      const res = patch ?? { ok: true, status: 200, body: { serial_number_prefix: sent } };
      return { ok: res.ok, status: res.status, json: async () => res.body };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ id: 1, serial_number_prefix: prefix }),
    };
  });
  return calls;
}

async function renderSection(opts = {}) {
  const calls = mockFetch(opts);
  const { default: SerialNumberSettingsSection } = await import(
    "../SerialNumberSettingsSection"
  );
  const { ToastProvider } = await import("../../Toast");
  // AdminSettings renders the section inside its main company-settings form.
  const section = opts.onFormSubmit ? (
    <form onSubmit={opts.onFormSubmit}>
      <SerialNumberSettingsSection />
    </form>
  ) : (
    <SerialNumberSettingsSection />
  );
  const utils = render(<ToastProvider>{section}</ToastProvider>);
  const input = await screen.findByLabelText("Serial Number Prefix");
  const save = screen.getByRole("button", { name: /Save Serial Prefix/i });
  return { ...utils, calls, input, save };
}

const patches = (calls) => calls.filter((c) => c.opts.method === "PATCH");

describe("normalizeSerialPrefix", () => {
  it.each([
    ["SN-", "SN-"],
    ["SN", "SN-"],
    ["  acme ", "acme-"],
    ["JOES-PS", "JOES-PS-"],
  ])("accepts %j as %j", (raw, value) => {
    expect(normalizeSerialPrefix(raw)).toEqual({ value });
  });

  it.each(["", "   ", "-SN", "SN_1", "S/N", "SN 1", "TOOLONGPREFIX"])(
    "rejects %j",
    (raw) => {
      expect(normalizeSerialPrefix(raw).error).toBeTruthy();
    },
  );
});

describe("SerialNumberSettingsSection", () => {
  it("shows the stored prefix and a preview", async () => {
    const { input, save } = await renderSection({ prefix: "BLB-" });
    expect(input.value).toBe("BLB-");
    expect(screen.getByText(/^BLB-\d{8}-0001$/)).toBeTruthy();
    expect(save.disabled).toBe(true); // nothing changed yet
  });

  it("saves the normalised prefix with a PATCH of only that field", async () => {
    const { input, save, calls } = await renderSection();
    fireEvent.change(input, { target: { value: "JOES" } });
    expect(screen.getByText(/^JOES-\d{8}-0001$/)).toBeTruthy();
    fireEvent.click(save);

    await waitFor(() => expect(patches(calls)).toHaveLength(1));
    const [patch] = patches(calls);
    expect(patch.url).toContain("/api/v1/settings/company");
    expect(JSON.parse(patch.opts.body)).toEqual({ serial_number_prefix: "JOES-" });
    await waitFor(() => expect(input.value).toBe("JOES-"));
    expect(await screen.findByText("Serial number prefix saved")).toBeTruthy();
  });

  it("Enter in the prefix field saves the prefix, not the enclosing form", async () => {
    const onFormSubmit = vi.fn((e) => e.preventDefault());
    const { input, calls } = await renderSection({ onFormSubmit });
    fireEvent.change(input, { target: { value: "ACME" } });

    const notPrevented = fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

    expect(notPrevented).toBe(false); // default (implicit form submit) cancelled
    await waitFor(() => expect(patches(calls)).toHaveLength(1));
    expect(JSON.parse(patches(calls)[0].opts.body)).toEqual({
      serial_number_prefix: "ACME-",
    });
    expect(onFormSubmit).not.toHaveBeenCalled();
  });

  it("flags an invalid prefix and does not send it", async () => {
    const { input, save, calls } = await renderSection();
    fireEvent.change(input, { target: { value: "S/N" } });
    expect(screen.getByText(/letters, digits and dashes only/i)).toBeTruthy();
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(save.disabled).toBe(true);
    fireEvent.click(save);
    expect(patches(calls)).toHaveLength(0);
  });

  it("shows the server's validation message when it rejects the prefix", async () => {
    const { input, save } = await renderSection({
      patch: {
        ok: false,
        status: 422,
        body: { detail: [{ msg: "Value error, Serial number prefix cannot be empty" }] },
      },
    });
    fireEvent.change(input, { target: { value: "ACME" } });
    fireEvent.click(save);
    expect(
      await screen.findByText("Serial number prefix cannot be empty"),
    ).toBeTruthy();
    expect(input.value).toBe("ACME"); // kept for correction
  });

  it("explains that only admins can change it", async () => {
    const { input, save } = await renderSection({
      patch: { ok: false, status: 403, body: { detail: "Admin access required" } },
    });
    fireEvent.change(input, { target: { value: "OPS" } });
    fireEvent.click(save);
    expect(
      await screen.findByText("Only admins can change the serial number prefix"),
    ).toBeTruthy();
  });
});
