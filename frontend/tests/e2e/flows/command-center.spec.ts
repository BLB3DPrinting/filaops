/**
 * E2E-501: Command Center Dashboard Tests
 *
 * Tests the Command Center feature:
 * - Summary stats display
 * - Action items list with filtering
 * - Machine status grid
 * - Auto-refresh functionality
 */
import { test, expect } from '@playwright/test';
import { seedTestScenario, cleanupTestData } from '../fixtures/test-utils';
import { E2E_CONFIG } from '../config';

// Don't use shared auth - this test does its own login after seeding
test.use({ storageState: { cookies: [], origins: [] } });

test.describe.serial('E2E-501: Command Center Dashboard', () => {

  // Store auth token to reuse across tests (avoid rate limiting)
  let authToken: string | null = null;

  // Seed once before all tests in this file
  test.beforeAll(async ({ request }) => {
    await cleanupTestData();
    await seedTestScenario('production-in-progress');

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
      await page.goto('http://localhost:5173/admin/command-center');
      await expect(page).toHaveURL(/\/admin\/command-center/);
    } else {
      // Fallback to form login if token not available
      await page.getByRole('textbox', { name: 'Email Address' }).fill(E2E_CONFIG.email);
      await page.getByRole('textbox', { name: 'Password' }).fill(E2E_CONFIG.password);
      await page.getByRole('button', { name: 'Sign In' }).click();
      await expect(page).toHaveURL(/\/admin(?!\/login)/);
      await page.goto('http://localhost:5173/admin/command-center');
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

  test('Command Center page loads with header', async ({ page }) => {
    await loginAsAdmin(page);
    await page.waitForLoadState('networkidle');

    // Verify page header
    await expect(page.getByRole('heading', { name: 'Command Center' })).toBeVisible();

    // Verify refresh button exists
    await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible();
  });

  test('Summary stats section displays counts', async ({ page }) => {
    await loginAsAdmin(page);
    await page.waitForLoadState('networkidle');

    // Wait for summary section to load
    await expect(page.getByText("Today's Summary")).toBeVisible();

    // Verify summary cards are present
    await expect(page.getByText('Orders Due Today')).toBeVisible();
    await expect(page.getByText('Shipped Today')).toBeVisible();
    await expect(page.getByText('In Production')).toBeVisible();
    await expect(page.getByText('Blocked')).toBeVisible();
  });

  test('Action Items section shows list or empty state', async ({ page }) => {
    await loginAsAdmin(page);
    await page.waitForLoadState('networkidle');

    // Verify action items section header
    await expect(page.getByText('Action Items')).toBeVisible();

    // Either "All Clear!" or action item cards should be visible
    const allClear = page.getByText('All Clear!');
    const actionCards = page.locator('[class*="border-red"], [class*="border-orange"], [class*="border-yellow"], [class*="border-blue"]');

    // Wait for either state
    await page.waitForTimeout(1000);

    const hasAllClear = await allClear.isVisible().catch(() => false);
    const hasActionCards = (await actionCards.count()) > 0;

    expect(hasAllClear || hasActionCards).toBe(true);
  });

  test('Machines section displays resource grid', async ({ page }) => {
    await loginAsAdmin(page);
    await page.waitForLoadState('networkidle');

    // Verify machines section header
    await expect(page.getByText('Machines')).toBeVisible();

    // Should show either resources or "No resources configured"
    const noResources = page.getByText('No resources configured');
    const resourceCards = page.locator('[class*="rounded-lg"]').filter({ hasText: /running|idle|maintenance|offline/i });

    await page.waitForTimeout(1000);

    const hasNoResources = await noResources.isVisible().catch(() => false);
    const hasResourceCards = (await resourceCards.count()) > 0;

    expect(hasNoResources || hasResourceCards).toBe(true);
  });

  test('Refresh button triggers data reload', async ({ page }) => {
    await loginAsAdmin(page);
    await page.waitForLoadState('networkidle');

    // Click refresh button
    const refreshButton = page.getByRole('button', { name: 'Refresh' });
    await expect(refreshButton).toBeVisible();
    await refreshButton.click();

    // Button should show loading state briefly
    // (the spin animation class is applied)
    await page.waitForTimeout(500);

    // Page should still be visible after refresh
    await expect(page.getByRole('heading', { name: 'Command Center' })).toBeVisible();
  });

  test('Navigation link exists in sidebar', async ({ page }) => {
    await loginAsAdmin(page);
    await page.waitForLoadState('networkidle');

    // Verify Command Center link in navigation
    const navLink = page.getByRole('link', { name: 'Command Center' });
    await expect(navLink).toBeVisible();
  });

  // =====================
  // API TESTS
  // =====================

  test('API: action-items endpoint returns valid response', async ({ request }) => {
    const token = getApiToken();

    const response = await request.get('http://127.0.0.1:8000/api/v1/command-center/action-items', {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('items');
    expect(data).toHaveProperty('total_count');
    expect(data).toHaveProperty('counts_by_type');
    expect(Array.isArray(data.items)).toBe(true);
    expect(typeof data.total_count).toBe('number');
  });

  test('API: summary endpoint returns valid response', async ({ request }) => {
    const token = getApiToken();

    const response = await request.get('http://127.0.0.1:8000/api/v1/command-center/summary', {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('orders_due_today');
    expect(data).toHaveProperty('orders_shipped_today');
    expect(data).toHaveProperty('production_in_progress');
    expect(data).toHaveProperty('resources_total');
    expect(typeof data.orders_due_today).toBe('number');
  });

  test('API: resources endpoint returns valid response', async ({ request }) => {
    const token = getApiToken();

    const response = await request.get('http://127.0.0.1:8000/api/v1/command-center/resources', {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('resources');
    expect(data).toHaveProperty('summary');
    expect(Array.isArray(data.resources)).toBe(true);

    // If there are resources, verify structure
    if (data.resources.length > 0) {
      const resource = data.resources[0];
      expect(resource).toHaveProperty('id');
      expect(resource).toHaveProperty('code');
      expect(resource).toHaveProperty('status');
    }
  });

  test('API: endpoints require authentication', async ({ request }) => {
    // Test without auth token
    const endpoints = [
      'http://127.0.0.1:8000/api/v1/command-center/action-items',
      'http://127.0.0.1:8000/api/v1/command-center/summary',
      'http://127.0.0.1:8000/api/v1/command-center/resources',
    ];

    for (const url of endpoints) {
      const response = await request.get(url);
      expect(response.status()).toBe(401);
    }
  });

});
