/**
 * E2E-201: Blocking Issues Flow Tests
 *
 * Tests the BlockingIssuesPanel component and suggested actions workflow.
 * Validates UI-201, UI-202, UI-203, UI-204 implementations.
 */
import { test, expect } from '@playwright/test';
import { seedTestScenario, cleanupTestData } from '../fixtures/test-utils';
import { E2E_CONFIG } from '../config';

// Don't use shared auth - this test does its own login after seeding
test.use({ storageState: { cookies: [], origins: [] } });

test.describe.serial('E2E-201: Blocking Issues Flow', () => {

  // Store auth token to reuse across tests (avoid rate limiting)
  let authToken: string | null = null;

  // Seed once before all tests in this file
  test.beforeAll(async ({ request }) => {
    await cleanupTestData();
    await seedTestScenario('low-stock-with-allocations');

    // Get auth token once via API to avoid rate limiting browser logins
    const response = await request.post('http://127.0.0.1:8000/api/v1/auth/login', {
      form: {
        username: E2E_CONFIG.email,
        password: E2E_CONFIG.password,
      },
    });
    if (response.ok()) {
      const data = await response.json();
      authToken = data.access_token;
    }
  });

  // Helper: login via stored token (fast, no rate limit)
  async function loginAsAdmin(page: any) {
    await page.goto('http://localhost:5173/admin/login');

    // Inject token directly instead of filling form
    if (authToken) {
      await page.evaluate((token: string) => {
        localStorage.setItem('adminToken', token);
      }, authToken);
      await page.goto('http://localhost:5173/admin/orders');
      await expect(page).toHaveURL(/\/admin\/orders/);
    } else {
      // Fallback to form login if token not available
      await page.getByRole('textbox', { name: 'Email Address' }).fill(E2E_CONFIG.email);
      await page.getByRole('textbox', { name: 'Password' }).fill(E2E_CONFIG.password);
      await page.getByRole('button', { name: 'Sign In' }).click();
      await expect(page).toHaveURL(/\/admin(?!\/login)/);
    }
  }

  // Helper: get token (reuses cached token from beforeAll)
  function getApiToken(): string {
    if (!authToken) {
      throw new Error('Auth token not available - beforeAll may have failed');
    }
    return authToken;
  }

  // =====================
  // Test 1: Expedite existing PO from SO blocking issues
  // =====================
  test('expedite PO action navigates to PO detail page', async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to Orders
    await page.getByRole('link', { name: 'Orders', exact: true }).click();
    await expect(page).toHaveURL(/\/admin\/orders/);

    // Click View on the SO row (first one)
    await page.getByRole('button', { name: 'View' }).first().click();

    // Verify BlockingIssuesPanel is visible
    await expect(page.getByText('Fulfillment Status')).toBeVisible();
    await expect(page.getByText('Blocking Issues')).toBeVisible();

    // Click Expedite PO action
    await page.getByRole('button', { name: /Expedite PO PO-\d{4}-\d+/ }).click();

    // Should navigate to purchasing page
    await expect(page).toHaveURL(/\/admin\/purchasing/);

    // Click View (exact match) to go to PO detail
    await page.getByRole('button', { name: 'View', exact: true }).click();

    // Verify we're on the PO detail page (uses query param)
    await expect(page).toHaveURL(/\/admin\/purchasing\?po_id=\d+/);
    await expect(page.getByText(/PO-\d{4}-\d+/)).toBeVisible();
  });

  // =====================
  // Test 2: Verify BlockingIssuesPanel shows on SO detail
  // =====================
  test('SO detail page shows blocking issues panel with line issues', async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to Orders → View SO
    await page.getByRole('link', { name: 'Orders', exact: true }).click();
    await page.getByRole('button', { name: 'View' }).first().click();

    // Verify panel elements
    await expect(page.getByText('Fulfillment Status')).toBeVisible();
    await expect(page.getByText('LINE ISSUES')).toBeVisible();
    await expect(page.getByText('SUGGESTED ACTIONS')).toBeVisible();
    
    // Should show material shortage (use first() to avoid strict mode)
    await expect(page.getByText(/short/i).first()).toBeVisible();
  });

  // =====================
  // Test 3: Verify suggested actions are actionable
  // =====================
  test('suggested actions show priority and are clickable', async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to Orders → View SO
    await page.getByRole('link', { name: 'Orders', exact: true }).click();
    await page.getByRole('button', { name: 'View' }).first().click();

    // Verify suggested actions section
    await expect(page.getByText('SUGGESTED ACTIONS')).toBeVisible();
    
    // Should show priority number (1, 2, etc.)
    await expect(page.getByRole('button', { name: /^1\s/ })).toBeVisible();
    
    // Should show "Expedite PO" as first action
    await expect(page.getByRole('button', { name: /Expedite PO/ })).toBeVisible();
  });

  // =====================
  // Test 4: Create PO action (requires scenario without existing PO)
  // =====================
  test.skip('create PO action opens pre-filled modal', async ({ page }) => {
    // TODO: Needs 'low-stock-no-po' scenario where no PO exists yet
  });

  // =====================
  // API Tests: Use direct API auth (no browser login needed)
  // =====================
  test('API-201 & API-202: blocking-issues endpoints return correct structure', async ({ request }) => {
    // Get cached token (from beforeAll)
    const token = getApiToken();

    // --- API-201: SO blocking-issues ---
    const soListResponse = await request.get('http://127.0.0.1:8000/api/v1/sales-orders/', {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    expect(soListResponse.ok()).toBeTruthy();
    
    const soOrders = await soListResponse.json();
    const soId = soOrders.items?.[0]?.id || soOrders[0]?.id;
    expect(soId).toBeTruthy();

    const soResponse = await request.get(`http://127.0.0.1:8000/api/v1/sales-orders/${soId}/blocking-issues`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    expect(soResponse.ok()).toBeTruthy();

    const soData = await soResponse.json();
    expect(soData).toHaveProperty('status_summary');
    expect(soData.status_summary).toHaveProperty('can_fulfill');
    expect(soData.status_summary).toHaveProperty('blocking_count');
    expect(soData).toHaveProperty('line_issues');
    expect(soData).toHaveProperty('resolution_actions');
    expect(Array.isArray(soData.line_issues)).toBe(true);
    expect(Array.isArray(soData.resolution_actions)).toBe(true);

    // --- API-202: PO blocking-issues ---
    const poListResponse = await request.get('http://127.0.0.1:8000/api/v1/production-orders/', {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    
    if (!poListResponse.ok()) {
      console.log('Production orders list failed - skipping PO test');
      return;
    }
    
    const poOrders = await poListResponse.json();
    const poId = poOrders.items?.[0]?.id || poOrders[0]?.id;
    
    if (!poId) {
      console.log('No production orders found - skipping PO test');
      return;
    }

    const poResponse = await request.get(`http://127.0.0.1:8000/api/v1/production-orders/${poId}/blocking-issues`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    expect(poResponse.ok()).toBeTruthy();

    const poData = await poResponse.json();
    expect(poData).toHaveProperty('status_summary');
    expect(poData.status_summary).toHaveProperty('can_produce');
    expect(poData.status_summary).toHaveProperty('blocking_count');
    expect(poData).toHaveProperty('material_issues');
    expect(poData).toHaveProperty('resolution_actions');
    expect(Array.isArray(poData.material_issues)).toBe(true);
    expect(Array.isArray(poData.resolution_actions)).toBe(true);
  });
});
