import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import AiSettingsSection from "../AiSettingsSection";
import { ToastProvider } from "../../Toast";

afterEach(() => {
  vi.restoreAllMocks();
});

const MODELS = {
  source: "anthropic",
  recommended: "claude-sonnet-5-5",
  pricing_url: "https://platform.claude.com/docs/en/about-claude/pricing",
  error: null,
  cached: false,
  models: [
    { id: "claude-opus-5-5", display_name: "Claude Opus 5.5", lifecycle: "active" },
    { id: "claude-sonnet-5-5", display_name: "Claude Sonnet 5.5", lifecycle: "active" },
  ],
};

function mockBackend(savedModel) {
  const calls = [];
  global.fetch = vi.fn().mockImplementation(async (url, opts = {}) => {
    const u = String(url);
    calls.push({ url: u, opts });
    const json = (body) => ({ ok: true, status: 200, json: async () => body });
    if (u.endsWith("/settings/ai") && !opts.method) {
      return json({
        ai_provider: "anthropic",
        ai_api_key_set: true,
        ai_api_key_masked: "sk-...abcd",
        ai_anthropic_model: savedModel,
        ai_status: "configured",
        external_ai_blocked: false,
      });
    }
    if (u.includes("/ai/anthropic-status")) return json({ installed: true, version: "x" });
    if (u.includes("/ai/anthropic-models")) return json(MODELS);
    if (u.endsWith("/ai/test")) return json({ success: true, provider: "anthropic", message: "ok" });
    return json({});
  });
  return calls;
}

function renderSection() {
  render(
    <ToastProvider>
      <AiSettingsSection />
    </ToastProvider>,
  );
}

describe("AiSettingsSection", () => {
  it("loads a saved invalid model ID with a warning instead of breaking", async () => {
    mockBackend("claude-haiku-3-5-20241022");
    renderSection();

    const select = await screen.findByLabelText("Model");
    await waitFor(() => expect(select.value).toBe("claude-haiku-3-5-20241022"));
    await waitFor(() => expect(select.options).toHaveLength(3));
    expect(select.options[0].textContent).toMatch(/not listed by Anthropic \(may be retired\)/);
    expect(screen.queryByText(/\/doc/)).toBeNull();
  });

  it("Test Connection checks the model picked in the form", async () => {
    const calls = mockBackend("claude-opus-4-5-20251101");
    renderSection();

    const select = await screen.findByLabelText("Model");
    await waitFor(() => expect(select.options.length).toBeGreaterThan(1));
    fireEvent.change(select, { target: { value: "claude-opus-5-5" } });
    fireEvent.click(screen.getByRole("button", { name: "Test Connection" }));

    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/ai/test"))).toBe(true));
    const testCall = calls.find((c) => c.url.endsWith("/ai/test"));
    expect(JSON.parse(testCall.opts.body)).toEqual({ ai_anthropic_model: "claude-opus-5-5" });
  });
});
