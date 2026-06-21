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
  // click the Routings TAB button (not the "Work Centers & Routings" page title, which "Routings" also matches)
  { name: 'production/02-routings-list', url: '/admin/manufacturing', actions: [{ clickSelector: 'button:has-text("Routings")' }, { wait: 800 }], full: true },
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

  // --- inventory (transactions page has a very long ledger; viewport keeps panels/form in focus) ---
  { name: 'inventory/01-transactions-page', url: '/admin/inventory/transactions', full: false },
  // inline form; the type <select> is the only one with a transfer option → To Location appears
  { name: 'inventory/02-new-transaction-form', url: '/admin/inventory/transactions', actions: [{ clickBtn: 'New Transaction' }, { selectOption: { selector: 'select:has(option[value="transfer"])', value: 'transfer' } }, { wait: 800 }], full: false },
  { name: 'inventory/03-pending-approvals', url: '/admin/inventory/transactions', actions: [{ click: 'Pending Approvals' }, { wait: 1000 }], full: false },
  { name: 'inventory/04-reconciliation-panel', url: '/admin/inventory/transactions', actions: [{ click: 'items needing a count' }, { wait: 1200 }], full: false },
  { name: 'inventory/05-spools-page', url: '/admin/spools', full: true },
  { name: 'inventory/06-add-spool-modal', url: '/admin/spools', actions: [{ clickBtn: 'Add Spool' }, { wait: 1000 }], full: false },
  { name: 'inventory/07-cycle-count-page', url: '/admin/inventory/cycle-count', full: true },
  // pre-fill all rows to system qty, override one to create a variance, then open the review modal
  { name: 'inventory/08-variance-review-modal', url: '/admin/inventory/cycle-count', actions: [{ clickBtn: 'Fill Current Qty' }, { wait: 600 }, { fill: { selector: 'input[type="number"]', value: '200' } }, { clickBtn: 'Submit Count' }, { wait: 1200 }], full: false },

  // --- reconciliation (panels on the transactions page; viewport keeps focus off the long ledger) ---
  { name: 'reconciliation/01-transactions-page-collapsed', url: '/admin/inventory/transactions', full: false },
  { name: 'reconciliation/02-reconciliation-expanded', url: '/admin/inventory/transactions', actions: [{ click: 'items needing a count' }, { wait: 1200 }], full: false },
  // expand the panel, then open the per-row Count dialog
  { name: 'reconciliation/03-count-dialog', url: '/admin/inventory/transactions', actions: [{ click: 'items needing a count' }, { wait: 1000 }, { clickBtn: 'Count' }, { wait: 800 }], full: false },
  // expand, open the dev/test fallback dialog, type the required confirmation to enable Run fallback
  { name: 'reconciliation/04-baseline-to-stored-dialog', url: '/admin/inventory/transactions', actions: [{ click: 'items needing a count' }, { wait: 1000 }, { click: 'Baseline to stored' }, { wait: 800 }, { fill: { selector: 'input[placeholder="BASELINE_TO_STORED"]', value: 'BASELINE_TO_STORED' } }, { wait: 400 }], full: false },

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

  // --- purchasing (tabs via ?tab=orders|vendors|import|low-stock|buy-list; modals are buttons) ---
  { name: 'purchasing/01-purchasing-overview', url: '/admin/purchasing', full: true },
  { name: 'purchasing/02-vendor-modal', url: '/admin/purchasing?tab=vendors', actions: [{ clickBtn: 'New Vendor' }, { wait: 1000 }], full: false },
  { name: 'purchasing/03-po-create-modal', url: '/admin/purchasing?tab=orders', actions: [{ clickBtn: 'New PO' }, { wait: 1200 }], full: false },
  // first "Receive" button belongs to the first ordered PO (5 ordered POs in demo)
  { name: 'purchasing/04-receive-modal', url: '/admin/purchasing?tab=orders', actions: [{ clickBtn: 'Receive' }, { wait: 1200 }], full: false },
  { name: 'purchasing/05-low-stock-tab', url: '/admin/purchasing?tab=low-stock', full: true },
  { name: 'purchasing/06-buy-list-tab', url: '/admin/purchasing?tab=buy-list', full: true },

  // --- printers / work centers (Core list view renders a card grid; HUD/Cards view is PRO) ---
  { name: 'printers/01-printers-list-table', url: '/admin/printers', full: true },
  // focus the single card that has a live Running active-work panel
  { name: 'printers/02-printer-card-active-work', url: '/admin/printers', actions: [{ wait: 1200 }], clip: '.bg-gray-800.rounded-xl:has-text("Running")' },
  { name: 'printers/03-network-discovery', url: '/admin/printers', actions: [{ click: 'Network Discovery' }, { wait: 1000 }], full: true },
  { name: 'printers/04-csv-import', url: '/admin/printers', actions: [{ click: 'CSV Import' }, { wait: 1000 }], full: true },
  { name: 'printers/05-maintenance-tab', url: '/admin/printers', actions: [{ click: 'Maintenance' }, { wait: 1200 }], full: true },
  { name: 'printers/06-work-centers-page', url: '/admin/manufacturing', full: true },
  { name: 'printers/07-routings-list', url: '/admin/manufacturing', actions: [{ clickSelector: 'button:has-text("Routings")' }, { wait: 800 }], full: true },

  // --- catalog (items + bom) ---
  { name: 'catalog/01-items-page-table-view', url: '/admin/items', full: true },
  { name: 'catalog/02-new-item-modal', url: '/admin/items', actions: [{ clickBtn: 'New Item' }, { wait: 1000 }], full: false },
  { name: 'catalog/03-new-material-form', url: '/admin/items', actions: [{ clickBtn: 'New Material' }, { wait: 1000 }], full: false },
  // filter to finished goods first so the first Duplicate target has a BOM (Swap rows)
  { name: 'catalog/04-duplicate-item-modal', url: '/admin/items', actions: [{ selectOption: { selector: 'select:has(option[value="finished_good"])', value: 'finished_good' } }, { wait: 800 }, { clickBtn: 'Duplicate' }, { wait: 1000 }], full: false },
  { name: 'catalog/05-bom-list', url: '/admin/bom', full: true },
  // BOM detail is a modal opened by the row View button
  { name: 'catalog/06-bom-detail', url: '/admin/bom', actions: [{ clickBtn: 'View' }, { wait: 1200 }], full: false },

  // --- mrp (buy list / low stock live under purchasing; material reqs on order detail) ---
  { name: 'mrp/01-buy-list-overview', url: '/admin/purchasing?tab=buy-list', full: true },
  // first chevron button expands the first buy-list row's demand/incoming detail
  { name: 'mrp/02-buy-list-row-expanded', url: '/admin/purchasing?tab=buy-list', actions: [{ clickSelector: 'table tbody tr button' }, { wait: 800 }], full: true },
  { name: 'mrp/03-low-stock-tab', url: '/admin/purchasing?tab=low-stock', full: true },
  { name: 'mrp/04-order-detail-material-requirements', url: '/admin/orders/1', actions: [{ wait: 1000 }], clip: '.bg-gray-900.rounded-xl:has-text("Material Requirements")' },

  // --- overview (index) ---
  { name: 'overview/01-sidebar-nav', url: '/admin', actions: [{ wait: 800 }], clip: 'aside' },
  { name: 'overview/02-command-center', url: '/admin', full: true },
  { name: 'overview/03-production-list', url: '/admin/production', full: true },

  // --- dashboard (command center only; Analytics is @require_tier(PRO) — excluded from Core docs) ---
  { name: 'dashboard/01-command-center-overview', url: '/admin', full: true },
  { name: 'dashboard/02-command-center-summary-cards', url: '/admin', actions: [{ wait: 900 }], clip: 'section:has-text("Today")' },
  { name: 'dashboard/03-command-center-action-items', url: '/admin', actions: [{ wait: 900 }], clip: 'section:has-text("Action Items")' },
  { name: 'dashboard/04-command-center-machines', url: '/admin', actions: [{ wait: 900 }], clip: 'section:has-text("Machines")' },
  // single idle FDM card carries the dispatch chip (NEXT UP / Confirm / Pick different)
  { name: 'dashboard/05-command-center-dispatch-chip', url: '/admin', actions: [{ wait: 900 }], clip: '.rounded-lg:has-text("FDM-03")' },

  // --- glossary (reuses cross-feature views) ---
  { name: 'glossary/02-command-center', url: '/admin', full: true },
  { name: 'glossary/03-mrp-planned-orders', url: '/admin/purchasing?tab=buy-list', full: true },
  { name: 'glossary/04-production-order-detail', url: '/admin/production', actions: [{ clickFirstRow: true }], full: true },
  { name: 'glossary/06-work-centers', url: '/admin/manufacturing', full: true },
  { name: 'glossary/01-bom-detail', url: '/admin/bom', actions: [{ clickBtn: 'View' }, { wait: 1200 }], full: false },
  // routing editor: the Routings TAB (button:has-text avoids matching the "Work Centers & Routings" title) → Edit
  { name: 'glossary/05-routing-editor', url: '/admin/manufacturing', actions: [{ clickSelector: 'button:has-text("Routings")' }, { wait: 800 }, { clickBtn: 'Edit' }, { wait: 1200 }], full: false },

  // --- system settings (settings/); price-levels is PRO and intentionally not captured ---
  { name: 'settings/01-company-settings-top', url: '/admin/settings', actions: [{ wait: 900 }], full: false },
  { name: 'settings/02-tax-settings', url: '/admin/settings', actions: [{ wait: 900 }], clip: '.bg-gray-800.rounded-lg:has-text("Tax Rates")' },
  { name: 'settings/03-locations', url: '/admin/locations', full: true },
  { name: 'settings/04-scrap-reasons', url: '/admin/scrap-reasons', full: true },
  { name: 'settings/06-integrations-ai', url: '/admin/integrations', actions: [{ wait: 900 }], full: true },

  // --- troubleshooting (settings clips + login) ---
  { name: 'troubleshooting/01-login-forgot-password', url: '/admin/login', actions: [{ wait: 800 }], full: false },
  { name: 'troubleshooting/02-settings-smtp-warning', url: '/admin/settings', actions: [{ wait: 900 }], clip: '.rounded-xl:has-text("Email (SMTP) Not Configured")' },
  { name: 'troubleshooting/04-settings-version-updates', url: '/admin/settings', actions: [{ wait: 900 }], clip: '.bg-gray-800.rounded-lg:has-text("Check for Updates")' },
  // tick "Show inactive locations" to reveal the staged inactive location + its Reactivate action
  { name: 'troubleshooting/03-locations-reactivate', url: '/admin/locations', actions: [{ click: 'Show inactive locations' }, { wait: 1200 }], full: true },

  // --- users ---
  { name: 'users/01-team-members-overview', url: '/admin/users', full: true },
  { name: 'users/02-add-user-modal', url: '/admin/users', actions: [{ clickBtn: 'Add User' }, { wait: 1000 }], full: false },
  // "Reset PW" is the per-row reset action; first row opens the reset-password modal
  { name: 'users/03-reset-password-modal', url: '/admin/users', actions: [{ clickBtn: 'Reset PW' }, { wait: 1000 }], full: false },
  { name: 'users/04-security-audit-overview', url: '/admin/security', full: true },
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
        if (a.selectOption) { await page.locator(a.selectOption.selector).first().selectOption(a.selectOption.value, { timeout: 8000 }).catch((e) => console.log('  select miss:', a.selectOption.selector, e.message.split('\n')[0])); await sleep(800); }
        if (a.clickSelector) { await page.locator(a.clickSelector).first().click({ timeout: 8000 }).catch((e) => console.log('  clickSel miss:', a.clickSelector, e.message.split('\n')[0])); await sleep(1000); }
        if (a.waitModal) { await page.locator('[role="dialog"], .modal, [class*="modal"]').first().waitFor({ timeout: 6000 }).catch(() => console.log('  modal not detected')); await sleep(800); }
        if (a.wait) await sleep(a.wait);
      }
      const file = path.join(OUT, s.name + '.png');
      fs.mkdirSync(path.dirname(file), { recursive: true });
      if (s.clip) {
        // element-scoped screenshot (focus a single card/section); falls back to viewport
        await page.locator(s.clip).first().screenshot({ path: file }).catch(async (e) => { console.log('  clip miss:', e.message.split('\n')[0]); await page.screenshot({ path: file }); });
      } else {
        await page.screenshot({ path: file, fullPage: !!s.full });
      }
      console.log('OK  ', s.name, s.clip ? '(clip)' : s.full ? '(full)' : '(viewport)');
      ok++;
    } catch (e) {
      console.log('FAIL', s.name, '-', e.message.split('\n')[0]);
      fail++;
    }
  }
  console.log(`\ndone: ${ok} ok, ${fail} fail`);
  await browser.close();
})();
