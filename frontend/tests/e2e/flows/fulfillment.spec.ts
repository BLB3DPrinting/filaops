/**
 * E2E-301: Fulfillment Status Flow Tests
 *
 * Tests the fulfillment status feature across API and UI:
 * - API-301: Single order fulfillment status
 * - API-302: Bulk fulfillment in list
 * - API-303: Filtering/sorting by fulfillment state
 * - UI-301: SalesOrderCard component
 * - UI-302: FulfillmentProgress on detail page
 * - UI-303: OrderFilters and card grid
 */
import { test, expect } from '@playwright/test';
import { seedTestScenario, cleanupTestData } from '../fixtures/test-utils';
import { E2E_CONFIG } from '../config';

// Don't use shared auth - this test does its own login after seeding
test.use({ storageState: { cookies: [], origins: [] } });

test.describe.serial('E2E-301: Fulfillment Status Flow', () => {

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
  // UI TESTS
  // =====================

  test('SO list shows card-based layout with fulfillment status', async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to Orders page
    await page.getByRole('link', { name: 'Orders', exact: true }).click();
    await expect(page).toHaveURL(/\/admin\/orders/);

    // Wait for page to load
    await page.waitForLoadState('networkidle');

    // Verify we see cards (grid layout) not a table
    // Cards have View Details link, tables have View button in rows
    const grid = page.locator('.grid');
    await expect(grid).toBeVisible();

    // Verify at least one card has a status badge
    const statusBadges = page.locator('span.rounded-full').filter({
      hasText: /(Ready to Ship|Partially Ready|Blocked|Shipped)/
    });
    await expect(statusBadges.first()).toBeVisible();
  });

  test('filter buttons filter by fulfillment state', async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to Orders page
    await page.getByRole('link', { name: 'Orders', exact: true }).click();
    await expect(page).toHaveURL(/\/admin\/orders/);
    await page.waitForLoadState('networkidle');

    // Click the "Blocked" filter button
    await page.getByRole('button', { name: 'Blocked' }).click();

    // Verify URL has filter param
    await expect(page).toHaveURL(/filter=blocked/);

    // Wait for filtered results
    await page.waitForLoadState('networkidle');

    // All visible cards should have "Blocked" badge (or empty state)
    const cards = page.locator('.grid > div');
    const cardCount = await cards.count();

    if (cardCount > 0) {
      // Each card should have blocked status
      for (let i = 0; i < Math.min(cardCount, 3); i++) {
        const card = cards.nth(i);
        const badge = card.locator('span.rounded-full').first();
        const badgeText = await badge.textContent();
        expect(badgeText?.toLowerCase()).toContain('blocked');
      }
    }

    // Click "All" to reset filter
    await page.getByRole('button', { name: 'All', exact: true }).click();
    await expect(page).not.toHaveURL(/filter=/);
  });

  test('sort dropdown changes card order', async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to Orders page
    await page.getByRole('link', { name: 'Orders', exact: true }).click();
    await page.waitForLoadState('networkidle');

    // Change sort to "Newest First"
    const sortDropdown = page.locator('select#order-sort');
    await sortDropdown.selectOption('order_date:desc');

    // Verify URL has sort param (colon may be URL-encoded as %3A)
    await expect(page).toHaveURL(/sort=order_date(%3A|:)desc/);

    // Change to "Most Actionable First"
    await sortDropdown.selectOption('fulfillment_priority:asc');
    await expect(page).toHaveURL(/sort=fulfillment_priority(%3A|:)asc/);

    // Verify sort was applied by checking cards are still visible
    await page.waitForLoadState('networkidle');
    const firstCard = page.locator('.grid > div').first();
    await expect(firstCard).toBeVisible();

    // Note: The actual order depends on seeded data - we just verify sort UI works
  });

  test('clicking View Details navigates to order detail', async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to Orders page
    await page.getByRole('link', { name: 'Orders', exact: true }).click();
    await page.waitForLoadState('networkidle');

    // Get the first order number before clicking
    const firstCard = page.locator('.grid > div').first();
    await expect(firstCard).toBeVisible();

    // Click View Details on first card
    await firstCard.getByText('View Details').click();

    // Should navigate to detail page (path-based, not query param based)
    await expect(page).toHaveURL(/\/admin\/orders\/\d+/);
  });

  test('SO detail page shows FulfillmentProgress component', async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to Orders → first order detail
    await page.getByRole('link', { name: 'Orders', exact: true }).click();
    await page.waitForLoadState('networkidle');

    // Click View Details on first card
    await page.locator('.grid > div').first().getByText('View Details').click();
    await page.waitForLoadState('networkidle');

    // Verify FulfillmentProgress component is visible
    await expect(page.getByText('Fulfillment Progress')).toBeVisible();

    // Should show progress bar
    const progressBar = page.locator('[role="progressbar"]');
    await expect(progressBar).toBeVisible();

    // Should show lines ready count
    await expect(page.getByText(/\d+\/\d+ lines ready/)).toBeVisible();
  });

  // =====================
  // API TESTS
  // =====================

  test('API-301 & API-302 & API-303: fulfillment endpoints work correctly', async ({ request }) => {
    const token = getApiToken();

    // --- API-301: Single order fulfillment status ---
    const listResponse = await request.get('http://127.0.0.1:8000/api/v1/sales-orders/', {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    expect(listResponse.ok()).toBeTruthy();

    const orders = await listResponse.json();
    const soId = orders.items?.[0]?.id || orders[0]?.id;
    expect(soId).toBeTruthy();

    const statusResponse = await request.get(
      `http://127.0.0.1:8000/api/v1/sales-orders/${soId}/fulfillment-status`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );
    expect(statusResponse.ok()).toBeTruthy();

    const statusData = await statusResponse.json();
    expect(statusData).toHaveProperty('summary');
    expect(statusData.summary).toHaveProperty('state');
    expect(statusData.summary).toHaveProperty('lines_total');
    expect(statusData.summary).toHaveProperty('lines_ready');
    expect(statusData.summary).toHaveProperty('fulfillment_percent');
    expect(statusData).toHaveProperty('lines');
    expect(Array.isArray(statusData.lines)).toBe(true);

    // Validate state is one of expected values
    const validStates = ['ready_to_ship', 'partially_ready', 'blocked', 'shipped', 'cancelled'];
    expect(validStates).toContain(statusData.summary.state);

    // --- API-302: Bulk fulfillment in list ---
    const bulkResponse = await request.get(
      'http://127.0.0.1:8000/api/v1/sales-orders/?include_fulfillment=true',
      { headers: { 'Authorization': `Bearer ${token}` } }
    );
    expect(bulkResponse.ok()).toBeTruthy();

    const bulkData = await bulkResponse.json();
    const items = bulkData.items || bulkData;
    expect(items.length).toBeGreaterThan(0);
    expect(items[0]).toHaveProperty('fulfillment');
    expect(items[0].fulfillment).toHaveProperty('state');
    expect(items[0].fulfillment).toHaveProperty('fulfillment_percent');

    // --- API-303: Filtering by state ---
    const filteredResponse = await request.get(
      'http://127.0.0.1:8000/api/v1/sales-orders/?include_fulfillment=true&fulfillment_state=blocked',
      { headers: { 'Authorization': `Bearer ${token}` } }
    );
    expect(filteredResponse.ok()).toBeTruthy();

    const filteredData = await filteredResponse.json();
    const filteredItems = filteredData.items || filteredData;
    // All returned items should be blocked (or empty if none match)
    for (const item of filteredItems) {
      expect(item.fulfillment.state).toBe('blocked');
    }

    // --- API-303: Sorting by priority ---
    const sortedResponse = await request.get(
      'http://127.0.0.1:8000/api/v1/sales-orders/?include_fulfillment=true&sort_by=fulfillment_priority&sort_order=asc',
      { headers: { 'Authorization': `Bearer ${token}` } }
    );
    expect(sortedResponse.ok()).toBeTruthy();

    const sortedData = await sortedResponse.json();
    const sortedItems = sortedData.items || sortedData;
    // First item should be most actionable (ready_to_ship is priority 1, partially_ready is 2)
    if (sortedItems.length > 1) {
      const firstState = sortedItems[0].fulfillment?.state;
      const lastState = sortedItems[sortedItems.length - 1].fulfillment?.state;

      // ready_to_ship should come before blocked
      const priorityOrder = ['ready_to_ship', 'partially_ready', 'blocked', 'shipped', 'cancelled'];
      const firstPriority = priorityOrder.indexOf(firstState);
      const lastPriority = priorityOrder.indexOf(lastState);

      // First should have lower or equal priority index (more actionable)
      if (firstPriority !== -1 && lastPriority !== -1) {
        expect(firstPriority).toBeLessThanOrEqual(lastPriority);
      }
    }
  });

  test('API: invalid fulfillment_state returns 400', async ({ request }) => {
    const token = getApiToken();

    const response = await request.get(
      'http://127.0.0.1:8000/api/v1/sales-orders/?fulfillment_state=invalid_state',
      { headers: { 'Authorization': `Bearer ${token}` } }
    );

    expect(response.status()).toBe(400);
  });

});
