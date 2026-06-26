import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

beforeEach(() => {
  vi.resetModules();
  // jsdom has no object-URL impl; the component uses it for blob thumbnails.
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

const jsonRes = (data) => ({ ok: true, status: 200, json: async () => data });
const blobRes = () => ({ ok: true, status: 200, blob: async () => new Blob(["x"]) });

function mockFetch({ list = [], postOk = true, listOk = true } = {}) {
  const calls = [];
  let current = [...list];
  let nextId = 100;
  global.fetch = vi.fn().mockImplementation(async (url, opts) => {
    const u = String(url);
    const method = opts?.method || "GET";
    calls.push({ url: u, method });
    if (u.includes("/download")) return blobRes();
    const del = u.match(/\/photos\/(\d+)$/);
    if (method === "DELETE" && del) {
      current = current.filter((p) => p.id !== Number(del[1]));
      return jsonRes({ id: Number(del[1]) });
    }
    if (method === "POST" && u.endsWith("/photos")) {
      if (!postOk) return { ok: false, status: 400, json: async () => ({ detail: "Upload failed" }) };
      const id = nextId++;
      current = [...current, { id, file_name: "new.png", caption: null, download_url: `/api/v1/production-orders/qc-inspections/1/photos/${id}/download` }];
      return { ok: true, status: 201, json: async () => ({ id }) };
    }
    if (u.endsWith("/photos")) {
      return listOk ? jsonRes(current) : { ok: false, status: 500, json: async () => ({}) };
    }
    return jsonRes({});
  });
  return calls;
}

async function renderPhotos(opts) {
  const calls = mockFetch(opts);
  const { default: QCInspectionPhotos } = await import("../QCInspectionPhotos");
  const { ToastProvider } = await import("../Toast");
  const utils = render(
    <ToastProvider>
      <QCInspectionPhotos inspectionId={1} />
    </ToastProvider>,
  );
  return { ...utils, calls };
}

describe("QCInspectionPhotos", () => {
  it("shows the empty state when there are no photos", async () => {
    await renderPhotos({ list: [] });
    await waitFor(() => expect(screen.getByText(/No photos attached/i)).toBeTruthy());
  });

  it("renders a thumbnail per photo", async () => {
    await renderPhotos({
      list: [{ id: 5, file_name: "rim.png", caption: "scratch on rim", download_url: "/api/v1/production-orders/qc-inspections/1/photos/5/download" }],
    });
    await waitFor(() => expect(screen.getByAltText("scratch on rim")).toBeTruthy());
  });

  it("uploads a picked file then shows it", async () => {
    const { calls } = await renderPhotos({ list: [] });
    await waitFor(() => screen.getByText(/No photos attached/i));
    const input = document.querySelector('input[type="file"]');
    const file = new File(["x"], "rim.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/photos"))).toBe(true),
    );
    await waitFor(() => expect(screen.getByAltText("new.png")).toBeTruthy());
  });

  it("shows a load error instead of the empty state when the list fails", async () => {
    await renderPhotos({ list: [], listOk: false });
    await waitFor(() => expect(screen.getByText(/load photos/i)).toBeTruthy());
    expect(screen.queryByText(/No photos attached/i)).toBeNull();
  });

  it("deletes a photo", async () => {
    const { calls } = await renderPhotos({
      list: [{ id: 5, file_name: "rim.png", caption: "scratch", download_url: "/api/v1/production-orders/qc-inspections/1/photos/5/download" }],
    });
    await waitFor(() => screen.getByAltText("scratch"));
    fireEvent.click(screen.getByTitle("Delete photo"));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    await waitFor(() => expect(screen.queryByAltText("scratch")).toBeNull());
  });
});
