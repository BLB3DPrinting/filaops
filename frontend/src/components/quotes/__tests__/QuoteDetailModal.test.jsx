import { render, screen, waitFor } from "@testing-library/react";
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

const renderModal = () => render(
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
    />
  </ToastProvider>,
);

describe("QuoteDetailModal attachments", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((url) => {
      if (String(url).endsWith("/api/v1/quotes/42")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(quote),
        });
      }
      if (String(url).endsWith("/api/v1/quotes/42/files")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            {
              id: 7,
              original_filename: "manual-part.stl",
              file_format: ".stl",
              file_size_bytes: 2048,
              file_hash: "a".repeat(64),
              uploaded_at: "2026-05-21T12:01:00Z",
              processed: false,
              processing_error: null,
            },
          ]),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    }));
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
    expect(screen.getAllByRole("button", { name: "Delete" }).length).toBeGreaterThan(0);
  });
});
