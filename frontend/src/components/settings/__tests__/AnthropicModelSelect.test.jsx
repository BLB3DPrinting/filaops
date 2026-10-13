import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import AnthropicModelSelect from "../AnthropicModelSelect";

afterEach(() => {
  vi.restoreAllMocks();
});

const LIVE = {
  source: "anthropic",
  recommended: "claude-sonnet-5-5",
  pricing_url: "https://platform.claude.com/docs/en/about-claude/pricing",
  error: null,
  cached: false,
  models: [
    { id: "claude-opus-5-5", display_name: "Claude Opus 5.5", lifecycle: "active" },
    { id: "claude-sonnet-5-5", display_name: "Claude Sonnet 5.5", lifecycle: "active" },
    { id: "claude-opus-4-5-20251101", display_name: "Claude Opus 4.5", lifecycle: "active" },
    { id: "claude-sonnet-4-20250514", display_name: "Claude Sonnet 4", lifecycle: "deprecated" },
  ],
};

const FALLBACK = {
  source: "fallback",
  recommended: "claude-sonnet-5-5",
  pricing_url: "https://platform.claude.com/docs/en/about-claude/pricing",
  error: "Anthropic rejected the API key (401). Check the key and save it again.",
  cached: false,
  models: [
    { id: "claude-fable-5-1", display_name: "Claude Fable 5.1", lifecycle: null },
    { id: "claude-opus-5-5", display_name: "Claude Opus 5.5", lifecycle: null },
    { id: "claude-sonnet-5-5", display_name: "Claude Sonnet 5.5", lifecycle: null },
    { id: "claude-haiku-5-5", display_name: "Claude Haiku 5.5", lifecycle: null },
  ],
};

function mockFetch(handler) {
  const calls = [];
  global.fetch = vi.fn().mockImplementation(async (url, opts) => {
    calls.push({ url: String(url), opts });
    return handler(String(url));
  });
  return calls;
}

const ok = (body) => ({ ok: true, status: 200, json: async () => body });

function renderSelect(props = {}) {
  const onChange = vi.fn();
  render(
    <AnthropicModelSelect
      value="claude-sonnet-5-5"
      savedModel="claude-sonnet-5-5"
      apiKeyMasked="sk-...abcd"
      onChange={onChange}
      {...props}
    />,
  );
  return { onChange };
}

const select = () => screen.getByLabelText("Model");
const optionTexts = () => Array.from(select().options).map((o) => o.textContent);

describe("AnthropicModelSelect", () => {
  it("lists the models Anthropic returns, marking recommended and deprecated", async () => {
    const calls = mockFetch(() => ok(LIVE));
    renderSelect();

    await waitFor(() => expect(select().options).toHaveLength(4));
    expect(calls[0].url).toContain("/api/v1/settings/ai/anthropic-models");
    expect(select().value).toBe("claude-sonnet-5-5");
    const texts = optionTexts();
    expect(texts).toContain("Claude Sonnet 5.5 (claude-sonnet-5-5) - recommended");
    expect(texts).toContain("Claude Sonnet 4 (claude-sonnet-4-20250514) - deprecated, retiring soon");
    expect(texts.join(" ")).not.toMatch(/\$/); // no per-document cost guesses
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("link", { name: /pricing/i }).getAttribute("href"))
      .toBe("https://platform.claude.com/docs/en/about-claude/pricing");
  });

  it("keeps a listed saved model (the owner's Opus 4.5) selected without a warning", async () => {
    mockFetch(() => ok(LIVE));
    renderSelect({ value: "claude-opus-4-5-20251101", savedModel: "claude-opus-4-5-20251101" });

    await waitFor(() => expect(select().options).toHaveLength(4));
    expect(select().value).toBe("claude-opus-4-5-20251101");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps a saved model Anthropic no longer lists, marked as possibly retired", async () => {
    mockFetch(() => ok(LIVE));
    renderSelect({ value: "claude-haiku-3-5-20241022", savedModel: "claude-haiku-3-5-20241022" });

    await waitFor(() => expect(select().options).toHaveLength(5));
    expect(select().value).toBe("claude-haiku-3-5-20241022");
    expect(optionTexts()[0]).toBe(
      "claude-haiku-3-5-20241022 - not listed by Anthropic (may be retired)",
    );
    expect(screen.getByRole("alert").textContent).toMatch(/does not list "claude-haiku-3-5-20241022"/);
  });

  it("lets the user move off an unlisted model", async () => {
    mockFetch(() => ok(LIVE));
    const { onChange } = renderSelect({
      value: "claude-haiku-3-5-20241022",
      savedModel: "claude-haiku-3-5-20241022",
    });
    await waitFor(() => expect(select().options).toHaveLength(5));

    fireEvent.change(select(), { target: { value: "claude-sonnet-5-5" } });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].target.name).toBe("ai_anthropic_model");
  });

  it("shows the fallback list and the backend's reason when Anthropic can't be asked", async () => {
    mockFetch(() => ok(FALLBACK));
    renderSelect({ value: "claude-opus-4-5-20251101", savedModel: "claude-opus-4-5-20251101" });

    await waitFor(() => expect(select().options).toHaveLength(5));
    expect(screen.getByRole("status").textContent).toMatch(/rejected the API key/);
    expect(optionTexts()[0]).toBe(
      "claude-opus-4-5-20251101 - saved value, not checked with Anthropic",
    );
    expect(select().value).toBe("claude-opus-4-5-20251101");
    expect(screen.getByRole("alert").textContent).toMatch(/could not be checked/);
  });

  it("keeps the saved model selectable when the request itself fails", async () => {
    mockFetch(() => ({ ok: false, status: 403, json: async () => ({ detail: "Admin access required" }) }));
    renderSelect({ value: "claude-opus-4-5-20251101", savedModel: "claude-opus-4-5-20251101" });

    await waitFor(() => expect(screen.getAllByRole("alert")[0].textContent).toMatch(/Admin access required/));
    expect(optionTexts()).toEqual([
      "claude-opus-4-5-20251101 - saved value, not checked with Anthropic",
    ]);
    expect(select().value).toBe("claude-opus-4-5-20251101");
  });

  it("handles a network error", async () => {
    mockFetch(() => {
      throw new Error("Failed to fetch");
    });
    renderSelect();
    await waitFor(() => expect(screen.getAllByRole("alert")[0].textContent).toMatch(/Failed to fetch/));
    expect(select().value).toBe("claude-sonnet-5-5");
  });

  it("refresh asks the backend to skip its cache", async () => {
    const calls = mockFetch(() => ok(LIVE));
    renderSelect();
    await waitFor(() => expect(select().options).toHaveLength(4));

    fireEvent.click(screen.getByRole("button", { name: "Refresh list" }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1].url).toContain("refresh=true");
  });

  it("reloads when a different API key is saved", async () => {
    const calls = mockFetch(() => ok(LIVE));
    const { rerender } = render(
      <AnthropicModelSelect value="claude-sonnet-5-5" savedModel="claude-sonnet-5-5"
        apiKeyMasked="sk-...aaaa" onChange={() => {}} />,
    );
    await waitFor(() => expect(calls).toHaveLength(1));
    rerender(
      <AnthropicModelSelect value="claude-sonnet-5-5" savedModel="claude-sonnet-5-5"
        apiKeyMasked="sk-...bbbb" onChange={() => {}} />,
    );
    await waitFor(() => expect(calls).toHaveLength(2));
  });
});
