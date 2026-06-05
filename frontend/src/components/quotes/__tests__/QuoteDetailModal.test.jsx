import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import QuoteDetailModal from "../QuoteDetailModal";
import { ToastProvider } from "../../Toast";

const quote = {
  id: 42,
  quote_number: "Q-2026-000042",
  product_name: "Manual Quote Part",
  quantity: 1,
  unit_price: "12.50",
  subtotal: "12.50",
  total_price: "12.50",
  status: "pending",
  customer_name: "Example Customer",
  customer_email: "customer@example.com",
  material_type: "PLA",
  color: "Black",
  has_image: false,
  line_count: 1,
  created_at: "2026-05-21T12:00:00Z",
  expires_at: "2026-08-19T12:00:00Z",
  sales_order_id: null,
  updated_at: "2026-05-21T12:00:00Z",
  approved_at: null,
  converted_at: null,
  lines: [],
};

const attachment = {
  id: 7,
  original_filename: "manual-part.stl",
  file_format: ".stl",
  file_size_bytes: 2048,
  file_hash: "a".repeat(64),
  uploaded_at: "2026-05-21T12:01:00Z",
  processed: false,
  processing_error: null,
};

let quoteFiles;
let detailQuote;

const renderModal = (props = {}) => render(
  <ToastProvider>
    <QuoteDetailModal
      quote={quote}
      onClose={vi.fn()}
      onEdit={vi.fn()}
      onUpdateStatus={vi.fn()}
      onConvert={vi.fn()}
      onDownloadPDF={vi.fn()}
      onPrintPDF={vi.fn()}
      onDuplicate={vi.fn()}
      onCopyLink={vi.fn()}
      onDelete={vi.fn()}
      getStatusStyle={() => "bg-gray-700 text-gray-200"}
      onRefresh={vi.fn()}
      {...props}
    />
  </ToastProvider>,
);

describe("QuoteDetailModal attachments", () => {
  beforeEach(() => {
    quoteFiles = [attachment];
    detailQuote = quote;
    vi.stubGlobal("confirm", vi.fn(() => true));
    vi.stubGlobal("fetch", vi.fn((url, options = {}) => {
      const method = options.method || "GET";
      if (String(url).endsWith("/api/v1/quotes/42")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(detailQuote),
        });
      }
      if (String(url).endsWith("/api/v1/quotes/42/files") && method === "GET") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(quoteFiles),
        });
      }
      if (String(url).endsWith("/api/v1/quotes/42/files") && method === "POST") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ ...attachment, id: 8, original_filename: "upload.stl" }),
        });
      }
      if (String(url).endsWith("/api/v1/quotes/42/files/7/download")) {
        return Promise.resolve({
          ok: true,
          blob: () => Promise.resolve(new Blob(["solid test"], { type: "model/stl" })),
        });
      }
      if (String(url).endsWith("/api/v1/quotes/42/files/7") && method === "DELETE") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ message: "Quote file deleted" }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    }));
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:quote-file");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows manual quote attachments with upload and download controls", async () => {
    renderModal();

    expect(screen.getByText("Quote Files")).toBeInTheDocument();
    expect(screen.getByText("Upload")).toBeInTheDocument();
    expect(screen.getByText("3MF, STL, OBJ, STEP, STP")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("manual-part.stl")).toBeInTheDocument();
    });

    expect(screen.getByText(".stl · 2.0 KB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download" })).toBeInTheDocument();
    const row = screen.getByText("manual-part.stl").closest("div").parentElement;
    expect(within(row).getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("uploads, downloads, and deletes quote attachments", async () => {
    const onRefresh = vi.fn();
    renderModal({ onRefresh });

    await waitFor(() => {
      expect(screen.getByText("manual-part.stl")).toBeInTheDocument();
    });

    const uploadInput = screen.getByText("Upload").closest("label").querySelector("input");
    fireEvent.change(uploadInput, {
      target: {
        files: [new File(["solid test"], "upload.stl", { type: "model/stl" })],
      },
    });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/quotes/42/files"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(onRefresh).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Download" }));
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/quotes/42/files/7/download"),
        expect.objectContaining({ credentials: "include" }),
      );
    });
    expect(URL.createObjectURL).toHaveBeenCalled();

    const row = screen.getByText("manual-part.stl").closest("div").parentElement;
    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/quotes/42/files/7"),
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("uses the empty quote-file panel as an upload target", () => {
    quoteFiles = [];
    renderModal();

    const emptyPanel = screen
      .getByText("Click to attach model files or customer-provided documents for this quote.")
      .closest("label");

    expect(emptyPanel.querySelector("input[type='file']")).toHaveAttribute(
      "accept",
      ".3mf,.stl,.obj,.step,.stp",
    );
  });

  it("passes fetched quote detail to edit and duplicate actions", async () => {
    const onEdit = vi.fn();
    const onDuplicate = vi.fn();
    detailQuote = {
      ...quote,
      line_count: 2,
      lines: [
        {
          id: 101,
          product_id: 201,
          product_name: "Bracket",
          quantity: 2,
          unit_price: "15.00",
          total: "30.00",
          material_type: "PETG",
          color: "Black",
          notes: null,
        },
        {
          id: 102,
          product_id: 202,
          product_name: "Clip",
          quantity: 1,
          unit_price: "5.00",
          total: "5.00",
          material_type: "PLA",
          color: "White",
          notes: null,
        },
      ],
    };

    renderModal({ onEdit, onDuplicate });

    await waitFor(() => {
      expect(screen.getByText("Items (2)")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Duplicate" }));

    expect(onEdit).toHaveBeenCalledWith(detailQuote);
    expect(onDuplicate).toHaveBeenCalledWith(detailQuote);
  });

  it("does not offer edit or delete actions after customer acceptance", async () => {
    quoteFiles = [];
    detailQuote = {
      ...quote,
      status: "accepted",
    };

    renderModal();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Convert to Order" })).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });
});
