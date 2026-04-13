import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Reset the shared apiClient singleton between tests so each test
// gets a fresh client that picks up the new global.fetch mock.
beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
});

const metricsData = {
  period_days: 30,
  total_inspections: 20,
  passed: 16,
  failed: 4,
  first_pass_yield: 80.0,
  pending_inspections: 3,
  scrap_rate: 2.5,
  total_scrapped_cost: 125.0,
};

const queueData = {
  items: [
    {
      id: 1,
      code: "PO-001",
      product_name: "Widget A",
      quantity_ordered: 100,
      quantity_completed: 50,
      qc_status: "pending",
      priority: 1,
    },
    {
      id: 2,
      code: "PO-002",
      product_name: "Widget B",
      quantity_ordered: 200,
      quantity_completed: 200,
      qc_status: "in_progress",
      priority: 2,
    },
  ],
  total: 2,
};

const recentData = [
  {
    id: 10,
    code: "PO-010",
    product_name: "Gadget C",
    qc_status: "passed",
    qc_inspected_by: "Alice",
    qc_inspected_at: "2026-03-01T12:00:00",
  },
  {
    id: 11,
    code: "PO-011",
    product_name: "Gadget D",
    qc_status: "failed",
    qc_inspected_by: "Bob",
    qc_inspected_at: "2026-03-02T12:00:00",
  },
];

const scrapData = [
  {
    reason_code: "PRINT_FAIL",
    reason_name: "Print Failure",
    count: 5,
    total_quantity: 15,
    total_cost: 75.0,
  },
  {
    reason_code: "MAT_DEFECT",
    reason_name: "Material Defect",
    count: 2,
    total_quantity: 4,
    total_cost: 50.0,
  },
];

function mockFetch(overrides = {}) {
  const responses = {
    metrics: overrides.metrics ?? metricsData,
    queue: overrides.queue ?? queueData,
    recent: overrides.recent ?? recentData,
    scrap: overrides.scrap ?? scrapData,
  };

  global.fetch = vi.fn().mockImplementation(async (url) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    let data;
    if (urlStr.includes("/quality/metrics")) data = responses.metrics;
    else if (urlStr.includes("/quality/inspection-queue"))
      data = responses.queue;
    else if (urlStr.includes("/quality/recent-inspections"))
      data = responses.recent;
    else if (urlStr.includes("/quality/scrap-summary")) data = responses.scrap;
    else data = {};

    return {
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => data,
      text: async () => JSON.stringify(data),
    };
  });
}

async function renderDashboard(fetchOverrides) {
  mockFetch(fetchOverrides);
  // Dynamic import after fetch mock is set, so the shared apiClient picks it up
  const { default: QualityDashboard } = await import("../QualityDashboard");
  return render(
    <MemoryRouter>
      <QualityDashboard />
    </MemoryRouter>,
  );
}

describe("QualityDashboard", () => {
  it("renders loading state initially", async () => {
    // Use a fetch that never resolves to keep loading visible
    global.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    const { default: QualityDashboard } = await import("../QualityDashboard");
    const { container } = render(
      <MemoryRouter>
        <QualityDashboard />
      </MemoryRouter>,
    );
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText("Quality Dashboard")).toBeInTheDocument();
  });

  it("renders stat cards with metric values", async () => {
    await renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("80%")).toBeInTheDocument();
    });
    expect(screen.getByText("First-Pass Yield")).toBeInTheDocument();
    expect(screen.getByText("Pending Inspections")).toBeInTheDocument();
    expect(screen.getByText("2.5%")).toBeInTheDocument();
    expect(screen.getByText("Scrap Rate")).toBeInTheDocument();
    expect(screen.getByText("Total Inspections")).toBeInTheDocument();
  });

  it("renders pending inspection count from metrics", async () => {
    await renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("3")).toBeInTheDocument();
    });
  });

  it("renders inspection queue items", async () => {
    await renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("PO-001")).toBeInTheDocument();
    });
    expect(screen.getByText("Widget A")).toBeInTheDocument();
    expect(screen.getByText("PO-002")).toBeInTheDocument();
    expect(screen.getByText("Widget B")).toBeInTheDocument();
    // Shows quantity progress
    expect(screen.getByText("50/100")).toBeInTheDocument();
    expect(screen.getByText("200/200")).toBeInTheDocument();
  });

  it("renders inspection queue items as links to production order", async () => {
    await renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("PO-001")).toBeInTheDocument();
    });
    const link = screen.getByText("PO-001").closest("a");
    expect(link).toHaveAttribute("href", "/admin/production/1");
  });

  it('renders "2 pending" in queue header', async () => {
    await renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("2 pending")).toBeInTheDocument();
    });
  });

  it("renders recent inspections with QC badges", async () => {
    await renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("PO-010")).toBeInTheDocument();
    });
    // Product name is combined with inspector: "Gadget C — by Alice"
    expect(screen.getByText(/Gadget C/)).toBeInTheDocument();
    expect(screen.getByText("passed")).toBeInTheDocument();
    expect(screen.getByText("PO-011")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("renders scrap summary table", async () => {
    await renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("Print Failure")).toBeInTheDocument();
    });
    expect(screen.getByText("PRINT_FAIL")).toBeInTheDocument();
    expect(screen.getByText("Material Defect")).toBeInTheDocument();
    expect(screen.getByText("MAT_DEFECT")).toBeInTheDocument();
    expect(screen.getByText("$75.00")).toBeInTheDocument();
    expect(screen.getByText("$50.00")).toBeInTheDocument();
  });

  it("shows empty inspection queue message", async () => {
    await renderDashboard({ queue: { items: [], total: 0 } });
    await waitFor(() => {
      expect(
        screen.getByText("No orders awaiting inspection"),
      ).toBeInTheDocument();
    });
  });

  it("shows empty recent inspections message", async () => {
    await renderDashboard({ recent: [] });
    await waitFor(() => {
      expect(
        screen.getByText("No inspections recorded yet"),
      ).toBeInTheDocument();
    });
  });

  it("hides scrap section when no scrap data", async () => {
    await renderDashboard({ scrap: [] });
    await waitFor(() => {
      expect(screen.getByText("Quality Dashboard")).toBeInTheDocument();
    });
    // Wait for loading to finish
    await waitFor(() => {
      expect(screen.getByText("First-Pass Yield")).toBeInTheDocument();
    });
    expect(
      screen.queryByText("Scrap by Reason (30 days)"),
    ).not.toBeInTheDocument();
  });

  it("renders dash when metrics are null", async () => {
    await renderDashboard({
      metrics: {
        first_pass_yield: null,
        scrap_rate: null,
        pending_inspections: 0,
        total_inspections: 0,
      },
    });
    await waitFor(() => {
      expect(screen.getByText("First-Pass Yield")).toBeInTheDocument();
    });
    // Null first_pass_yield should show —
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it("shows QC badge with correct status text", async () => {
    await renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("pending")).toBeInTheDocument();
    });
    expect(screen.getByText("in progress")).toBeInTheDocument();
  });
});
