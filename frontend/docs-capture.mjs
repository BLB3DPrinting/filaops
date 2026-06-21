// Reusable docs screenshot capture for FilaOps Core.
// Usage: node docs-capture.mjs [section]   (run from frontend/ so 'playwright' resolves)
// Captures into ../docs/assets/screenshots/<name>.png against the running demo app.
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const BASE = process.env.DOCS_BASE || 'http://localhost:5174';
const OUT = path.resolve('../docs/assets/screenshots');
const EMAIL = process.env.DOCS_EMAIL || 'admin@acme-demo.test';
const PASS = process.env.DOCS_PASS || 'DocsDemo123!';
const only = process.argv[2] || null; // optional section filter

// shot = { name, url, full?, actions?[] }  actions: {click} | {clickBtn} | {clickFirstRow} | {waitModal} | {wait}
const SHOTS = [
  // --- production (pilot, already captured) ---
  { name: 'production/01-manufacturing-setup', url: '/admin/manufacturing', full: true },
  { name: 'production/02-routings-list', url: '/admin/manufacturing', actions: [{ click: 'Routings' }], full: true },
  { name: 'production/03-production-queue-view', url: '/admin/production', full: true },
  { name: 'production/04-scheduler-gantt', url: '/admin/production', actions: [{ click: 'Scheduler' }], full: false },
  { name: 'production/05-production-order-detail', url: '/admin/production', actions: [{ clickFirstRow: true }], full: true },
  { name: 'production/06-schedule-operation-modal', url: '/admin/production', actions: [{ click: 'Scheduler' }, { clickBtn: 'Schedule' }, { waitModal: true }], full: false },

  // --- orders ---
  { name: 'orders/01-customers-list', url: '/admin/customers', full: true },
  { name: 'orders/02-quotes-list', url: '/admin/quotes', full: true },
  { name: 'orders/03-orders-list', url: '/admin/orders', full: true },
  // wizard modal has no role=dialog; validateStep(1) always passes so Continue advances to step 2
  { name: 'orders/04-wizard-step1-customer', url: '/admin/orders', actions: [{ clickBtn: 'Create Order' }, { wait: 1500 }], full: false },
  { name: 'orders/05-wizard-step2-products', url: '/admin/orders', actions: [{ clickBtn: 'Create Order' }, { wait: 1200 }, { clickBtn: 'Continue' }, { wait: 1200 }], full: false },
  // order rows aren't <tr>; clickFirstRow fails — navigate directly (valid ids: 1,2,3)
  { name: 'orders/06-order-detail-workflow', url: '/admin/orders/1', full: true },
  { name: 'orders/07-shipping-page', url: '/admin/shipping', full: true },
  { name: 'orders/08-payments-page', url: '/admin/payments', full: true },

  // --- inventory ---
  { name: 'inventory/01-transactions-page', url: '/admin/inventory/transactions', full: true },
  { name: 'inventory/05-spools-page', url: '/admin/spools', full: true },
  { name: 'inventory/07-cycle-count-page', url: '/admin/inventory/cycle-count', full: true },

  // --- reconciliation ---
  { name: 'reconciliation/01-transactions-page-collapsed', url: '/admin/inventory/transactions', full: true },

  // --- accounting (tabs are <button>; exact labels from AdminAccounting.jsx) ---
  { name: 'accounting/01-accounting-dashboard', url: '/admin/accounting', full: true },
  { name: 'accounting/02-accounting-dashboard-cards', url: '/admin/accounting', full: false },
  // widen the journal date range (default is last 30d; demo orders are dated earlier in 2026)
  { name: 'accounting/03-sales-journal', url: '/admin/accounting', actions: [{ clickBtn: 'Sales Journal' }, { fill: { selector: 'input[type="date"]', value: '2026-01-01' } }], full: true },
  { name: 'accounting/04-payments-journal', url: '/admin/accounting', actions: [{ clickBtn: 'Payments' }], full: true },
  { name: 'accounting/05-cogs-tab', url: '/admin/accounting', actions: [{ clickBtn: 'COGS & Materials' }], full: true },
  { name: 'accounting/06-tax-center', url: '/admin/accounting', actions: [{ clickBtn: 'Tax Center' }], full: true },
  { name: 'accounting/07-invoices-list', url: '/admin/invoices', full: true },
  // invoice rows are <tr>; clicking opens a fetch-backed detail modal (no role=dialog) — wait after
  { name: 'accounting/08-invoice-detail', url: '/admin/invoices', actions: [{ clickFirstRow: true }, { wait: 1500 }], full: false },
  { name: 'accounting/09-payments-list', url: '/admin/payments', full: true },

  // --- purchasing ---
  { name: 'purchasing/01-purchasing-overview', url: '/admin/purchasing', full: true },

  // --- printers / work centers ---
  { name: 'printers/01-printers-list-table', url: '/admin/printers', full: true },
  { name: 'printers/06-work-centers-page', url: '/admin/manufacturing', full: true },
  { name: 'printers/07-routings-list', url: '/admin/manufacturing', actions: [{ click: 'Routings' }], full: true },

  // --- catalog (items) ---
  { name: 'catalog/01-items-list', url: '/admin/items', full: true },
  { name: 'catalog/02-bom-list', url: '/admin/bom', full: true },

  // --- mrp (buy list / low stock live under purchasing) ---
  { name: 'mrp/01-buy-list-overview', url: '/admin/purchasing', actions: [{ click: 'Buy List' }], full: true },

  // --- quality ---
  { name: 'quality/01-quality-dashboard', url: '/admin/quality', full: true },

  // --- settings / users ---
  { name: 'settings/01-system-settings', url: '/admin/settings', full: true },
  { name: 'users/01-users-list', url: '/admin/users', full: true },

  // --- dashboard (command center + analytics) ---
  { name: 'dashboard/01-command-center', url: '/admin', full: true },
  { name: 'dashboard/02-analytics', url: '/admin/analytics', full: true },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);

  // --- login ---
  await page.goto(BASE + '/admin/login', { waitUntil: 'networkidle' });
  await page.fill('#email', EMAIL);
  await page.fill('#password', PASS);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/admin**', { timeout: 20000 }).catch(() => {});
  await page.waitForLoadState('networkidle').catch(() => {});
  await sleep(1500);
  console.log('logged in, at', page.url());

  let ok = 0, fail = 0;
  for (const s of SHOTS) {
    if (only && !s.name.startsWith(only)) continue;
    try {
      await page.goto(BASE + s.url, { waitUntil: 'networkidle' });
      await sleep(1500);
      for (const a of s.actions || []) {
        if (a.click) { await page.getByText(a.click, { exact: false }).first().click({ timeout: 8000 }).catch((e) => console.log('  click miss:', a.click, e.message.split('\n')[0])); await sleep(1200); }
        if (a.clickBtn) { await page.getByRole('button', { name: new RegExp(a.clickBtn + '\\s*$') }).first().click({ timeout: 8000 }).catch((e) => console.log('  btn miss:', a.clickBtn, e.message.split('\n')[0])); await sleep(1000); }
        if (a.clickFirstRow) { await page.locator('table tbody tr').first().click({ timeout: 8000 }).catch((e) => console.log('  row miss:', e.message.split('\n')[0])); await page.waitForLoadState('networkidle').catch(() => {}); await sleep(1500); }
        if (a.fill) { await page.locator(a.fill.selector).first().fill(a.fill.value, { timeout: 8000 }).catch((e) => console.log('  fill miss:', a.fill.selector, e.message.split('\n')[0])); await page.waitForLoadState('networkidle').catch(() => {}); await sleep(1200); }
        if (a.waitModal) { await page.locator('[role="dialog"], .modal, [class*="modal"]').first().waitFor({ timeout: 6000 }).catch(() => console.log('  modal not detected')); await sleep(800); }
        if (a.wait) await sleep(a.wait);
      }
      const file = path.join(OUT, s.name + '.png');
      fs.mkdirSync(path.dirname(file), { recursive: true });
      await page.screenshot({ path: file, fullPage: !!s.full });
      console.log('OK  ', s.name, s.full ? '(full)' : '(viewport)');
      ok++;
    } catch (e) {
      console.log('FAIL', s.name, '-', e.message.split('\n')[0]);
      fail++;
    }
  }
  console.log(`\ndone: ${ok} ok, ${fail} fail`);
  await browser.close();
})();
