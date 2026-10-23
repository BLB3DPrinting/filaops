import { describe, it, expect, vi, afterEach } from "vitest";
import api from "./axios";

const respond = (body, { status = 200, contentType } = {}) =>
  new Response(body, {
    status,
    headers: contentType ? { "content-type": contentType } : {},
  });

const mockFetch = (res) => vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("axios wrapper empty responses", () => {
  it("returns null data for a 200 with an empty body and no content-type", async () => {
    mockFetch(respond("", {}));
    await expect(api.get("/x")).resolves.toEqual({ data: null, status: 200 });
  });

  it("returns null data for a 200 with an empty JSON body", async () => {
    mockFetch(respond("", { contentType: "application/json" }));
    await expect(api.get("/x")).resolves.toEqual({ data: null, status: 200 });
  });

  it("returns null data for a 204 with a JSON content-type", async () => {
    mockFetch(respond(null, { status: 204, contentType: "application/json" }));
    await expect(api.patch("/x", {})).resolves.toEqual({ data: null, status: 204 });
  });

  it("parses JSON and returns text for non-empty bodies", async () => {
    mockFetch(respond('{"a":1}', { contentType: "application/json" }));
    await expect(api.get("/x")).resolves.toEqual({ data: { a: 1 }, status: 200 });
    mockFetch(respond("hi", { contentType: "text/plain" }));
    await expect(api.get("/x")).resolves.toEqual({ data: "hi", status: 200 });
  });
});
