import { describe, it, expect, vi, afterEach } from "vitest";
import { createApiClient, ApiError } from "./apiClient";

// Build a real Response so res.json()/res.text() behave like the browser's.
const respond = (body, { status = 200, contentType } = {}) =>
  new Response(body, {
    status,
    headers: contentType ? { "content-type": contentType } : {},
  });

const mockFetch = (res) => {
  const fn = vi.fn().mockResolvedValue(res);
  vi.stubGlobal("fetch", fn);
  return fn;
};

const api = () => createApiClient({ baseUrl: "http://test" });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiClient success responses", () => {
  it("returns null for 204 even with a JSON content-type", async () => {
    mockFetch(respond(null, { status: 204, contentType: "application/json" }));
    await expect(api().delete("/api/v1/admin/bom/1")).resolves.toBeNull();
  });

  it("returns null for 205", async () => {
    mockFetch(respond(null, { status: 205 }));
    await expect(api().post("/x", {})).resolves.toBeNull();
  });

  it("returns null for a 200 with an empty body and JSON content-type", async () => {
    mockFetch(respond("", { contentType: "application/json" }));
    await expect(api().get("/x")).resolves.toBeNull();
  });

  it("returns null for a 200 with an empty body and no content-type", async () => {
    mockFetch(respond("", {}));
    await expect(api().get("/x")).resolves.toBeNull();
  });

  it("parses a 200 JSON body", async () => {
    mockFetch(respond('{"id":7,"name":"a"}', { contentType: "application/json" }));
    await expect(api().get("/x")).resolves.toEqual({ id: 7, name: "a" });
  });

  it("returns plain text for a 200 text body", async () => {
    mockFetch(respond("hello", { contentType: "text/plain" }));
    await expect(api().get("/x")).resolves.toBe("hello");
  });

  it("still parses JSON sent without a JSON content-type", async () => {
    mockFetch(respond('{"ok":true}', { contentType: "text/plain" }));
    await expect(api().get("/x")).resolves.toEqual({ ok: true });
  });
});

describe("apiClient error responses", () => {
  it("throws ApiError with the detail message and payload", async () => {
    mockFetch(
      respond('{"detail":"nope"}', { status: 400, contentType: "application/json" })
    );
    const err = await api().delete("/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.message).toBe("nope");
    expect(err.payload).toEqual({ detail: "nope" });
  });

  it("falls back to HTTP <status> when the error body is not JSON", async () => {
    mockFetch(respond("", { status: 404 }));
    const err = await api().get("/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe("HTTP 404");
  });
});
