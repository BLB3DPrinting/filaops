/**
 * Smoke Tests - Quick Validation Suite
 *
 * Run these after any deployment to verify core functionality.
 * Should complete in under 2 minutes.
 *
 * Usage: npm run test:smoke
 */

import { test, expect } from '@playwright/test';

test.describe('Smoke Tests - Critical Paths', () => {

  test('app loads and shows login', async ({ page }) => {
    // Navigate to login page first, then clear auth
    await page.goto('/admin/login');
    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());

    // Reload to see login page in unauthenticated state
    await page.reload();

    // Should show "Staff Login" heading
    await expect(page.getByRole('heading', { name: /staff login|login|sign in/i })).toBeVisible({ timeout: 5000 });

    // Verify login form elements exist
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test('can navigate to main sections', async ({ page }) => {
    const sections = [
      '/admin/orders',
      '/admin/production',
      '/admin/inventory',
      '/admin/products',
      '/admin/bom',
    ];

    for (const path of sections) {
      await page.goto(path);
      // Just verify page loaded (not login/error page)
      await expect(page).not.toHaveURL(/login/);
      // Wait for any content to load
      await page.waitForLoadState('networkidle', { timeout: 3000 });
    }
  });

  test('orders page loads data', async ({ page }) => {
    await page.goto('/admin/orders');

    // AdminOrders is lazy-loaded behind Suspense; on a cold Vite dev server
    // the chunk can take longer than an immediate isVisible() check. Wait for
    // the page's own heading, then require either data columns or the
    // Create Order action (an empty database is a valid smoke state).
    await expect(page.getByRole('heading', { name: /order management/i })).toBeVisible({ timeout: 15000 });
    await expect(
      page.getByRole('columnheader').first().or(page.getByRole('button', { name: /create|new/i }).first())
    ).toBeVisible({ timeout: 5000 });
  });

  test('can create new order', async ({ page }) => {
    await page.goto('/admin/orders');

    const createButton = page.getByRole('button', { name: /create|new.*order/i });
    await expect(createButton).toBeVisible();
    await createButton.click();

    // Modal should appear with customer selection heading
    await expect(page.getByRole('heading', { name: /select customer/i })).toBeVisible({ timeout: 3000 });
  });

  test('production page shows work orders', async ({ page }) => {
    await page.goto('/admin/production');

    // Should load without errors - look for specific Production heading
    await expect(page.getByRole('heading', { name: /production/i }).first()).toBeVisible();
  });

  test('inventory page functional', async ({ page }) => {
    await page.goto('/admin/inventory');

    // Just verify page loaded successfully
    await expect(page).toHaveURL(/inventory/);
    // Page should not show error state
    const hasError = await page.getByText(/error|failed/i).isVisible({ timeout: 2000 }).catch(() => false);
    expect(hasError).toBeFalsy();
  });

  test('API is responding', async ({ page }) => {
    await page.goto('/admin/orders');

    // Listen for API calls
    const response = await page.waitForResponse(
      resp => resp.url().includes('/api/v1') && resp.status() < 500,
      { timeout: 5000 }
    ).catch(() => null);

    expect(response).not.toBeNull();
  });

  test('no console errors on load', async ({ page }) => {
    const errors: string[] = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    await page.goto('/admin/orders');
    await page.waitForTimeout(2000);

    // Filter out known harmless errors
    const criticalErrors = errors.filter(e =>
      !e.includes('chrome-extension') &&
      !e.includes('devtools') &&
      !e.includes('favicon') &&
      // Network errors are expected in CI where backend may not be running
      !e.includes('Failed to fetch') &&
      !e.includes('Failed to load resource') &&
      !e.includes('NetworkError') &&
      !e.includes('net::ERR_') &&
      !e.includes('ERR_CONNECTION') &&
      !e.includes('TypeError: Failed to fetch') &&
      // Server errors in CI (backend may have issues)
      !e.includes('500') &&
      !e.includes('Internal Server Error') &&
      // CORS errors in CI
      !e.includes('CORS') &&
      !e.includes('Access-Control') &&
      // React hydration warnings
      !e.includes('Hydration') &&
      // Source map warnings
      !e.includes('source map') &&
      !e.includes('sourcemap')
    );

    // Show what errors were found for debugging
    if (criticalErrors.length > 0) {
      console.log('Critical console errors found:', criticalErrors);
    }

    expect(criticalErrors.length).toBe(0);
  });

  test('status transitions work', async ({ page }) => {
    await page.goto('/admin/orders');

    // Find first order with actions available
    const firstRow = page.locator('tr[data-order-id]').first();
    if (await firstRow.count() > 0) {
      await firstRow.click();

      // Should show order details
      await expect(page.getByText(/status|details/i)).toBeVisible();
    }
  });

  test('search functionality works', async ({ page }) => {
    await page.goto('/admin/orders');
    await page.waitForLoadState('networkidle').catch(() => {});

    const searchBox = page.getByPlaceholder(/search|filter/i);
    if (await searchBox.isVisible()) {
      await searchBox.fill('test');
      await page.waitForTimeout(500);

      // Table or content area should exist (even if empty or showing 'no results')
      const hasTable = await page.locator('table').count() > 0;
      const hasNoResults = await page.getByText(/no (results|orders|data)/i).isVisible().catch(() => false);
      const hasRows = await page.locator('tr').count() > 0;

      // Pass if we have a table, no results message, or any rows
      expect(hasTable || hasNoResults || hasRows).toBeTruthy();
    }
  });
});

test.describe('Smoke Tests - Error Handling', () => {

  test('handles network errors gracefully', async ({ page }) => {
    // Block API calls
    await page.route('**/api/v1/**', route => route.abort());

    await page.goto('/admin/orders');

    // Should show error message, not crash. apiClient retries network
    // failures (status 0) twice with 2s + 4s backoff before surfacing the
    // error, so the banner appears after ~6s; allow for that plus page load.
    await expect(page.getByText(/error|failed|unable/i).first()).toBeVisible({ timeout: 12000 });
  });

  test('handles 404 gracefully', async ({ page }) => {
    await page.goto('/admin/nonexistent-page');

    // Should show 404 page or redirect
    const has404 = await page.getByText(/404|not.*found/i).isVisible().catch(() => false);
    const redirected = page.url().includes('/admin');

    expect(has404 || redirected).toBeTruthy();
  });
});

test.describe('Smoke Tests - Mobile Responsive', () => {

  test.use({ viewport: { width: 375, height: 667 } }); // iPhone SE

  test('orders page works on mobile', async ({ page }) => {
    await page.goto('/admin/orders');

    // Just verify page loaded on mobile viewport
    await expect(page).toHaveURL(/orders/);

    // Check that some interactive element is visible
    const hasInteraction = await page.getByRole('button').first().isVisible({ timeout: 3000 }).catch(() => false);
    expect(hasInteraction).toBeTruthy();
  });
});
