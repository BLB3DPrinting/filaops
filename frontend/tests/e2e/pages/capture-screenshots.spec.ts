import { test, expect, Page } from '@playwright/test';
import { E2E_CONFIG } from '../config';
import * as fs from 'fs';

/**
 * Screenshot Capture Test
 *
 * Captures screenshots of all admin pages for SOP documentation.
 * Run: npm run test:e2e -- capture-screenshots.spec.ts
 */

const SCREENSHOT_DIR = 'docs/screenshots/sop';

// Ensure screenshot directory exists
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

// Helper to dismiss any modal that appears
async function dismissModals(page: Page) {
  // First click "Don't show this again" checkbox if present
  const dontShowAgain = page.locator('text="Don\'t show this again"');
  if (await dontShowAgain.count() > 0) {
    await dontShowAgain.click();
    await page.waitForTimeout(200);
  }

  // Dismiss the FilaOps Pro promotional modal
  const gotItBtn = page.locator('text="Got it, thanks!"');
  if (await gotItBtn.count() > 0) {
    await gotItBtn.click();
    await page.waitForTimeout(300);
  }

  // Also try clicking the X button if present
  const closeBtn = page.locator('[class*="modal"] button:has-text("×"), [class*="modal"] [aria-label="Close"]');
  if (await closeBtn.count() > 0) {
    await closeBtn.first().click();
    await page.waitForTimeout(300);
  }
}

// Helper to capture screenshot
async function screenshot(page: Page, name: string) {
  const path = `${SCREENSHOT_DIR}/${name}.png`;
  await page.screenshot({ path, fullPage: true });
  console.log(`Captured: ${path}`);
}

// Pages to capture
const PAGES = [
  { url: '/admin', name: 'dashboard-page', title: 'Dashboard' },
  { url: '/admin/quotes', name: 'quotes-page', title: 'Quotes' },
  { url: '/admin/orders', name: 'orders-page', title: 'Orders' },
  { url: '/admin/customers', name: 'customers-page', title: 'Customers' },
  { url: '/admin/items', name: 'items-page', title: 'Items' },
  { url: '/admin/production', name: 'production-page', title: 'Production' },
  { url: '/admin/bom', name: 'bom-page', title: 'Bill of Materials' },
  { url: '/admin/purchasing', name: 'purchasing-page', title: 'Purchasing' },
  { url: '/admin/manufacturing', name: 'manufacturing-page', title: 'Work Centers & Routings' },
  { url: '/admin/shipping', name: 'shipping-page', title: 'Shipping' },
  { url: '/admin/payments', name: 'payments-page', title: 'Payments' },
  { url: '/admin/settings', name: 'settings-page', title: 'Settings' },
];

test.describe('Screenshot Capture', () => {
  test('Capture all admin page screenshots', async ({ page, request }) => {
    const baseUrl = 'http://127.0.0.1:8001';

    // Step 1: Ensure admin exists
    const setupStatus = await request.get(`${baseUrl}/api/v1/setup/status`);
    const statusData = await setupStatus.json();

    if (statusData.needs_setup) {
      console.log('Creating admin account...');
      await request.post(`${baseUrl}/api/v1/setup/initial-admin`, {
        data: {
          email: E2E_CONFIG.email,
          password: E2E_CONFIG.password,
          full_name: E2E_CONFIG.name,
          company_name: 'Test Company'
        }
      });
    }

    // Step 2: Login via UI
    await page.goto('/admin/login');
    await page.waitForLoadState('networkidle');

    await page.fill('input[type="email"]', E2E_CONFIG.email);
    await page.fill('input[type="password"]', E2E_CONFIG.password);
    await page.click('button[type="submit"]');

    // Wait for redirect away from login
    await page.waitForFunction(() => !window.location.href.includes('/login'), { timeout: 15000 });
    console.log('Logged in successfully');

    // Dismiss the FilaOps Pro promotional modal if it appears
    await page.waitForTimeout(1000);
    const promoModal = page.locator('text="Got it, thanks!"');
    if (await promoModal.count() > 0) {
      await promoModal.click();
      console.log('Dismissed promotional modal');
      await page.waitForTimeout(500);
    }

    // Step 3: Capture screenshots of all pages
    for (const pageInfo of PAGES) {
      console.log(`Navigating to ${pageInfo.title}...`);
      await page.goto(pageInfo.url);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500); // Brief pause for rendering

      // Verify we're not redirected to login
      if (page.url().includes('/login')) {
        console.error(`Redirected to login when trying to access ${pageInfo.url}`);
        continue;
      }

      // Dismiss any modals that appear
      await dismissModals(page);
      await page.waitForTimeout(200);

      await screenshot(page, pageInfo.name);
    }

    // Step 4: Capture some modals
    console.log('Capturing modals...');

    // New Quote modal
    await page.goto('/admin/quotes');
    await page.waitForLoadState('networkidle');
    const newQuoteBtn = page.locator('button:has-text("New Quote")').first();
    if (await newQuoteBtn.count() > 0) {
      await newQuoteBtn.click();
      await page.waitForTimeout(1000);
      await screenshot(page, 'quotes-new-modal');
      await page.keyboard.press('Escape');
    }

    // Add Customer modal
    await page.goto('/admin/customers');
    await page.waitForLoadState('networkidle');
    const addCustomerBtn = page.locator('button:has-text("Add Customer"), button:has-text("New Customer")').first();
    if (await addCustomerBtn.count() > 0) {
      await addCustomerBtn.click();
      await page.waitForTimeout(1000);
      await screenshot(page, 'customers-add-modal');
      await page.keyboard.press('Escape');
    }

    console.log('\n=== Screenshot capture complete! ===');
    console.log(`Screenshots saved to: ${SCREENSHOT_DIR}/`);
  });
});
