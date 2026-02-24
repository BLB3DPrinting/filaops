import { test as baseTest, expect, Page, BrowserContext } from '@playwright/test';
import * as fs from 'fs';

/**
 * Walkthrough Screenshot Test — "Storybook" Customer Journey
 *
 * Walks through a complete customer lifecycle capturing numbered screenshots
 * at each step. Output is usable as a visual user manual / SOP documentation.
 *
 * Prerequisites:
 *   - Dev backend running on port 8000 (uvicorn app.main:app --port 8000)
 *   - Dev frontend running on port 5173 (npm run dev)
 *   - Dev DB seeded (python -m scripts.seed_dev_data)
 *
 * Run:
 *   npm run test:walkthrough
 *   # or
 *   npx playwright test --project=walkthrough
 */

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const DEV_EMAIL = 'admin@filaops.dev';
const DEV_PASSWORD = 'FilaOps2026!';
const SCREENSHOT_DIR = 'docs/screenshots/walkthrough';
const API_BASE = 'http://localhost:8000';

// Test customer we'll create via the UI (unique email per run)
const RUN_ID = Date.now().toString().slice(-6);
const NEW_CUSTOMER = {
  email: `alex+${RUN_ID}@storybookdemo.com`,
  firstName: 'Alex',
  lastName: 'Rivera',
  company: 'Storybook Demo Co.',
  phone: '555-867-5309',
  address: '742 Evergreen Terrace',
  city: 'Springfield',
  state: 'OR',
  zip: '97477',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Ensure output directory exists
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function capture(page: Page, name: string) {
  const path = `${SCREENSHOT_DIR}/${name}.png`;
  await page.screenshot({ path, fullPage: true });
  console.log(`  [screenshot] ${path}`);
}

async function dismissModals(page: Page) {
  await page.waitForTimeout(500);

  // Dismiss "Got it, thanks!" promo modal
  const gotIt = page.locator('button:has-text("Got it, thanks!")');
  if (await gotIt.isVisible({ timeout: 800 }).catch(() => false)) {
    await gotIt.click();
    await page.waitForTimeout(300);
  }

  // Dismiss "Don't show this again" checkbox + close
  const dontShow = page.locator('text="Don\'t show this again"');
  if (await dontShow.isVisible({ timeout: 300 }).catch(() => false)) {
    await dontShow.click();
    await page.waitForTimeout(200);
  }

  // Generic modal close button
  const closeBtn = page.locator(
    '[class*="modal"] button:has-text("x"), [class*="modal"] [aria-label="Close"]'
  );
  if (await closeBtn.first().isVisible({ timeout: 300 }).catch(() => false)) {
    await closeBtn.first().click();
    await page.waitForTimeout(300);
  }
}

async function waitForPage(page: Page) {
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(400); // let rendering settle
}

/**
 * Fetch a production order ID by status using the backend API.
 * Runs fetch from within the browser context so httpOnly cookies are included.
 */
async function findProductionOrderId(
  page: Page,
  status: string
): Promise<number | null> {
  return page.evaluate(
    async ({ apiBase, st }) => {
      const res = await fetch(
        `${apiBase}/api/v1/production-orders?status=${st}&limit=1`,
        { credentials: 'include' }
      );
      if (!res.ok) return null;
      const data = await res.json();
      const items = data.items || data;
      return Array.isArray(items) && items.length > 0 ? items[0].id : null;
    },
    { apiBase: API_BASE, st: status }
  );
}

// ---------------------------------------------------------------------------
// Test: self-contained auth (dev credentials, not test harness)
// ---------------------------------------------------------------------------

const test = baseTest;

// ---------------------------------------------------------------------------
// Walkthrough Steps (serial — state shared across tests)
// ---------------------------------------------------------------------------

test.describe.serial('Customer Walkthrough', () => {
  let page: Page;
  let context: BrowserContext;

  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext({
      baseURL: process.env.BASE_URL || 'http://localhost:5173',
    });
    page = await context.newPage();

    // Login with dev seed credentials
    await page.goto('/admin/login');
    await page.waitForLoadState('networkidle');
    await page.fill('input[type="email"]', DEV_EMAIL);
    await page.fill('input[type="password"]', DEV_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/admin(?!\/login)/, { timeout: 15000 });
    await page.waitForLoadState('networkidle');
    await dismissModals(page);
  });

  test.afterAll(async () => {
    await page.close();
    await context.close();
  });

  // ── 01: Dashboard ──────────────────────────────────────────────────────

  test('01 - Dashboard Overview', async () => {
    await page.goto('/admin');
    await waitForPage(page);
    await dismissModals(page);
    await capture(page, '01-dashboard-overview');
  });

  // ── 02: Customer List ──────────────────────────────────────────────────

  test('02 - Customer List', async () => {
    await page.goto('/admin/customers');
    await waitForPage(page);

    // Verify customers table loaded with seed data
    await expect(page.locator('tbody tr').first()).toBeVisible({
      timeout: 10000,
    });
    await capture(page, '02-customer-list');
  });

  // ── 03: Create Customer Form ──────────────────────────────────────────

  test('03 - Create Customer Form', async () => {
    const addBtn = page.locator('button:has-text("Add Customer")');
    await expect(addBtn).toBeVisible({ timeout: 5000 });
    await addBtn.click();
    await page.waitForTimeout(500);

    // Fill the form inside the modal overlay
    const modal = page.locator('.fixed');

    const emailInput = modal.locator('input[type="email"]').first();
    if (await emailInput.isVisible().catch(() => false)) {
      await emailInput.fill(NEW_CUSTOMER.email);
    }

    const inputs = modal.locator('input[type="text"], input:not([type])');
    const inputCount = await inputs.count();

    for (let i = 0; i < inputCount; i++) {
      const input = inputs.nth(i);
      const placeholder =
        (await input.getAttribute('placeholder').catch(() => '')) || '';
      const name = (await input.getAttribute('name').catch(() => '')) || '';
      const id = (await input.getAttribute('id').catch(() => '')) || '';

      if (
        name.includes('first') ||
        id.includes('first') ||
        placeholder.includes('First')
      ) {
        await input.fill(NEW_CUSTOMER.firstName);
      } else if (
        name.includes('last') ||
        id.includes('last') ||
        placeholder.includes('Last')
      ) {
        await input.fill(NEW_CUSTOMER.lastName);
      } else if (
        name.includes('phone') ||
        id.includes('phone') ||
        placeholder.includes('555')
      ) {
        await input.fill(NEW_CUSTOMER.phone);
      } else if (
        name.includes('company') ||
        id.includes('company') ||
        placeholder.includes('Company')
      ) {
        await input.fill(NEW_CUSTOMER.company);
      }
    }

    // Label-based fallback
    const firstNameLabel = modal.locator('label:has-text("First Name")');
    if (await firstNameLabel.isVisible().catch(() => false)) {
      const forId = await firstNameLabel.getAttribute('for');
      if (forId) {
        await modal.locator(`#${forId}`).fill(NEW_CUSTOMER.firstName);
      }
    }

    await capture(page, '03-create-customer-form');
  });

  // ── 04: Customer Created ──────────────────────────────────────────────

  test('04 - Customer Created', async () => {
    const modal = page.locator('.fixed');
    const submitBtn = modal.locator('button:has-text("Create Customer")');

    if (await submitBtn.isVisible().catch(() => false)) {
      await submitBtn.click();
      await page.waitForTimeout(2000);
      await waitForPage(page);
    } else {
      const submit = modal.locator('button[type="submit"]');
      if (await submit.isVisible().catch(() => false)) {
        await submit.click();
        await page.waitForTimeout(2000);
        await waitForPage(page);
      }
    }

    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(300);

    await page.goto('/admin/customers');
    await waitForPage(page);
    await capture(page, '04-customer-created');
  });

  // ── 05: Items Catalog ─────────────────────────────────────────────────

  test('05 - Items Catalog', async () => {
    await page.goto('/admin/items');
    await waitForPage(page);

    await expect(page.locator('tbody tr').first()).toBeVisible({
      timeout: 10000,
    });
    await capture(page, '05-items-catalog');
  });

  // ── 06: Item Detail ───────────────────────────────────────────────────

  test('06 - Item Detail (Finished Good)', async () => {
    const fgRow = page
      .locator('tbody tr:has-text("Headphone Wall Mount")')
      .first();

    if (await fgRow.isVisible({ timeout: 3000 }).catch(() => false)) {
      const editBtn = fgRow.locator('button:has-text("Edit")');
      await editBtn.click();
      await page.waitForTimeout(1000);
      await waitForPage(page);
      await capture(page, '06-item-detail-finished-good');

      await page.keyboard.press('Escape').catch(() => {});
      await page.waitForTimeout(300);
    } else {
      await capture(page, '06-item-detail-finished-good');
    }
  });

  // ── 07: BOM Detail ────────────────────────────────────────────────────

  test('07 - Bill of Materials', async () => {
    await page.goto('/admin/bom');
    await waitForPage(page);

    await expect(page.locator('tbody tr').first()).toBeVisible({
      timeout: 10000,
    });
    await capture(page, '07-bom-list');

    const firstRow = page.locator('tbody tr').first();
    const viewBtn = firstRow
      .locator('button:has-text("View"), button:has-text("Edit")')
      .first();
    if (await viewBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await viewBtn.click();
      await page.waitForTimeout(1000);
      await waitForPage(page);
      await capture(page, '07b-bom-detail');

      await page.keyboard.press('Escape').catch(() => {});
      await page.waitForTimeout(300);
    }
  });

  // ── 08: Manufacturing / Routings ──────────────────────────────────────

  test('08 - Manufacturing Routings', async () => {
    await page.goto('/admin/manufacturing');
    await waitForPage(page);

    const routingsTab = page.getByRole('button', { name: /Routings/i });
    if (await routingsTab.isVisible({ timeout: 3000 }).catch(() => false)) {
      await routingsTab.click();
      await page.waitForTimeout(1000);
      await waitForPage(page);
    }

    await capture(page, '08-manufacturing-routings');

    const firstRouting = page.locator('tbody tr').first();
    const viewBtn = firstRouting
      .locator('button:has-text("View"), button:has-text("Edit")')
      .first();
    if (await viewBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await viewBtn.click();
      await page.waitForTimeout(1000);
      await waitForPage(page);
      await capture(page, '08b-routing-operations');

      await page.keyboard.press('Escape').catch(() => {});
      await page.waitForTimeout(300);
    }
  });

  // ── 09: Sales Orders List ─────────────────────────────────────────────

  test('09 - Sales Orders List', async () => {
    await page.goto('/admin/orders');
    await waitForPage(page);

    // Orders page uses a CARD GRID (SalesOrderCard), not a table.
    // Each card has a "View Details" button.
    await expect(
      page.locator('button:has-text("View Details")').first()
    ).toBeVisible({ timeout: 10000 });

    await capture(page, '09-sales-orders-list');
  });

  // ── 10: Create Sales Order (Wizard) ───────────────────────────────────

  test('10 - Create Sales Order', async () => {
    // Open the Sales Order Wizard modal
    const createBtn = page.locator('button:has-text("Create Order")');
    await expect(createBtn).toBeVisible({ timeout: 5000 });
    await createBtn.click();
    await page.waitForTimeout(1000);

    const modal = page.locator('.fixed');

    // ── Step 1: Select Customer ──
    // Customer selection is a native <select> dropdown
    const customerSelect = modal.locator('select').first();
    await expect(customerSelect).toBeVisible({ timeout: 5000 });
    // Index 0 = "Walk-in / No Customer", 1+ = real customers
    await customerSelect.selectOption({ index: 1 });
    await page.waitForTimeout(500);

    await capture(page, '10a-order-wizard-customer');

    // Wizard uses "Continue" button (not "Next")
    const continueBtn1 = modal.locator('button:has-text("Continue")');
    await expect(continueBtn1).toBeVisible({ timeout: 3000 });
    await continueBtn1.click();
    await page.waitForTimeout(1500);

    // ── Step 2: Add Products ──
    // Products are displayed as clickable <button class="text-left"> cards
    // with a .font-mono child for the SKU. Only products with BOM are shown.
    const productBtn = modal.locator('button:has(.font-mono)').first();
    await expect(productBtn).toBeVisible({ timeout: 10000 });
    await productBtn.click();
    await page.waitForTimeout(500);

    // Set quantity on the line item
    const qtyInput = modal.locator('input[type="number"]').first();
    if (await qtyInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await qtyInput.clear();
      await qtyInput.fill('5');
    }

    await capture(page, '10b-order-wizard-products');

    // Continue to Review step
    const continueBtn2 = modal.locator('button:has-text("Continue")');
    await expect(continueBtn2).toBeVisible({ timeout: 3000 });
    await continueBtn2.click();
    await page.waitForTimeout(1000);

    await capture(page, '10c-order-wizard-review');

    // Submit the order
    const submitBtn = modal.locator('button:has-text("Create Sales Order")');
    await expect(submitBtn).toBeVisible({ timeout: 5000 });
    await submitBtn.click();
    await page.waitForTimeout(2000);
    await waitForPage(page);
  });

  // ── 11: Sales Order Detail ────────────────────────────────────────────

  test('11 - Sales Order Detail', async () => {
    // After wizard closes, reload orders to pick up the new order
    await page.goto('/admin/orders');
    await waitForPage(page);

    // Click "View Details" on the first order card (newest first)
    const viewBtn = page.locator('button:has-text("View Details")').first();
    await expect(viewBtn).toBeVisible({ timeout: 10000 });
    await viewBtn.click();

    // "View Details" navigates to /admin/orders/:id (Order Command Center)
    await page.waitForURL(/\/admin\/orders\/\d+/, { timeout: 10000 });
    await waitForPage(page);

    // Wait for actual order content to render (not just "Loading order...")
    await expect(
      page.locator('h1:has-text("Order:")')
    ).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(500);

    await capture(page, '11-sales-order-detail');
  });

  // ── 12: Production Orders ──────────────────────────────────────────────

  test('12 - Production Orders', async () => {
    await page.goto('/admin/production');
    await waitForPage(page);

    // Production page uses a real <table> via ProductionQueueList
    await page.locator('table tbody tr').first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {
      console.warn('  [walkthrough] Production table rows not visible — capturing as-is');
    });
    await capture(page, '12-production-orders');
  });

  // ── 13: Production Order Detail ───────────────────────────────────────

  test('13 - Production Order Detail', async () => {
    // Find a production order via API and navigate to its detail page
    const orderId =
      (await findProductionOrderId(page, 'released')) ||
      (await findProductionOrderId(page, 'draft')) ||
      (await findProductionOrderId(page, 'in_progress'));

    if (orderId) {
      await page.goto(`/admin/production/${orderId}`);
      await waitForPage(page);
      await capture(page, '13-production-order-detail');
    } else {
      // Fallback: screenshot the production list
      await capture(page, '13-production-order-detail');
    }
  });

  // ── 14: Release Production Order ──────────────────────────────────────

  test('14 - Release Production Order', async () => {
    // Find a Draft production order
    const draftId = await findProductionOrderId(page, 'draft');

    if (draftId) {
      // Navigate to Production Order Command Center
      await page.goto(`/admin/production/${draftId}`);
      await waitForPage(page);

      // Detail page shows "Release" button for draft orders
      const releaseBtn = page.getByRole('button', {
        name: 'Release',
        exact: true,
      });
      await expect(releaseBtn).toBeVisible({ timeout: 5000 });
      await capture(page, '14a-production-before-release');

      await releaseBtn.click();
      await page.waitForTimeout(2000);

      // The UI release may fail if materials aren't allocated.
      // Fall back to force-release via API if the status didn't change.
      const startBtn14 = page.getByRole('button', {
        name: 'Start Production',
        exact: true,
      });
      if (!(await startBtn14.isVisible({ timeout: 3000 }).catch(() => false))) {
        // Force-release through the API (bypasses allocation check)
        await page.evaluate(
          async ({ apiBase, id }) => {
            await fetch(
              `${apiBase}/api/v1/production-orders/${id}/release?force=true`,
              { method: 'POST', credentials: 'include' }
            );
          },
          { apiBase: API_BASE, id: draftId }
        );
        await page.reload();
        await waitForPage(page);
        await expect(
          page.locator('h1:has-text("Production Order:")')
        ).toBeVisible({ timeout: 10000 });
      }
      await page.waitForTimeout(500);
      await capture(page, '14b-production-released');
    } else {
      await capture(page, '14-production-no-draft');
    }
  });

  // ── 15: Start Production ──────────────────────────────────────────────

  test('15 - Start Production', async () => {
    // Find a Released production order
    const releasedId = await findProductionOrderId(page, 'released');

    if (releasedId) {
      await page.goto(`/admin/production/${releasedId}`);
      await waitForPage(page);

      // Detail page shows "Start Production" button for released orders
      const startBtn = page.getByRole('button', {
        name: 'Start Production',
        exact: true,
      });
      await expect(startBtn).toBeVisible({ timeout: 5000 });
      await capture(page, '15a-production-before-start');

      await startBtn.click();

      // Wait for status to update: "Start Production" disappears, "Complete" appears
      await expect(
        page.getByRole('button', { name: 'Complete', exact: true })
      ).toBeVisible({ timeout: 10000 });
      await page.waitForTimeout(500);
      await capture(page, '15b-production-started');
    } else {
      await capture(page, '15-production-no-released');
    }
  });

  // ── 16: Complete Production ───────────────────────────────────────────

  test('16 - Complete Production', async () => {
    // Find an In Progress production order
    const ipId = await findProductionOrderId(page, 'in_progress');

    if (ipId) {
      await page.goto(`/admin/production/${ipId}`);
      await waitForPage(page);

      // Detail page shows "Complete" button for in_progress orders
      const completeBtn = page.getByRole('button', {
        name: 'Complete',
        exact: true,
      });
      await expect(completeBtn).toBeVisible({ timeout: 5000 });
      await capture(page, '16a-production-completing');

      await completeBtn.click();

      // Wait for the Complete button to disappear (order is now complete)
      await expect(completeBtn).toBeHidden({ timeout: 10000 });
      await page.waitForTimeout(500);
      await waitForPage(page);
      await capture(page, '16b-production-completed');
    } else {
      await capture(page, '16-production-no-in-progress');
    }
  });

  // ── 17: Shipping ──────────────────────────────────────────────────────

  test('17 - Shipping', async () => {
    await page.goto('/admin/shipping');
    await waitForPage(page);
    await capture(page, '17-shipping-page');
  });

  // ── 18: Purchasing Overview ───────────────────────────────────────────

  test('18 - Purchasing & Inventory', async () => {
    // Purchasing page
    await page.goto('/admin/purchasing');
    await waitForPage(page);
    await page.locator('tbody tr').first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {
      console.warn('  [walkthrough] Purchasing table rows not visible — capturing as-is');
    });
    await capture(page, '18a-purchasing');

    // Items page (shows inventory On Hand column)
    await page.goto('/admin/items');
    await waitForPage(page);
    await capture(page, '18b-inventory-levels');

    // Final dashboard
    await page.goto('/admin');
    await waitForPage(page);
    await capture(page, '18c-final-dashboard');
  });
});
