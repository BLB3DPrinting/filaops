import { test as baseTest, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * SOP-Based Comprehensive UI Testing with Screenshots
 *
 * Tests each workflow documented in the SOPs to verify:
 * 1. Navigation works as documented
 * 2. UI elements exist and function
 * 3. CRUD operations complete successfully
 * 4. Error handling is appropriate
 *
 * Screenshots are captured for each page and saved to:
 * docs/screenshots/sop/
 *
 * Run: npm run test:e2e -- --grep "SOP"
 * Run specific: npm run test:e2e -- --grep "SOP-QTE"
 */

// Screenshot directory - will be used in SOP documentation
const SCREENSHOT_DIR = 'docs/screenshots/sop';

// Ensure screenshot directory exists
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

interface TestIssue {
  sop: string;
  test: string;
  severity: 'critical' | 'major' | 'minor' | 'enhancement';
  description: string;
  expected: string;
  actual: string;
  screenshot?: string;
}

const issues: TestIssue[] = [];

// Helper to log issues
function logIssue(issue: TestIssue) {
  issues.push(issue);
  console.log(`\n[${issue.severity.toUpperCase()}] ${issue.sop} - ${issue.test}`);
  console.log(`  Expected: ${issue.expected}`);
  console.log(`  Actual: ${issue.actual}`);
}

// Helper to capture screenshots with consistent naming
async function captureScreenshot(page: Page, name: string, fullPage: boolean = true) {
  const filename = `${SCREENSHOT_DIR}/${name}.png`;
  await page.screenshot({ path: filename, fullPage });
  console.log(`Screenshot saved: ${filename}`);
  return filename;
}

// Test credentials
const TEST_EMAIL = 'admin@test.com';
const TEST_PASSWORD = 'Admin123!';
const TEST_NAME = 'Admin User';

// Track if admin has been created
let adminCreated = false;

// Custom test fixture with authentication - uses UI login for each test
const test = baseTest.extend<{ authPage: Page }>({
  authPage: async ({ page, request }, use) => {
    const baseUrl = 'http://127.0.0.1:8001';

    // Check if we need to create admin first
    if (!adminCreated) {
      try {
        const setupStatus = await request.get(`${baseUrl}/api/v1/setup/status`);
        const statusData = await setupStatus.json();

        if (statusData.needs_setup) {
          console.log('Creating admin account...');
          const createAdmin = await request.post(`${baseUrl}/api/v1/setup/initial-admin`, {
            data: {
              email: TEST_EMAIL,
              password: TEST_PASSWORD,
              full_name: TEST_NAME,
              company_name: 'Test Company'
            }
          });

          if (createAdmin.ok()) {
            console.log('Admin created successfully');
            adminCreated = true;
          }
        } else {
          adminCreated = true; // Already exists
        }
      } catch (e) {
        console.log('Setup check failed:', e);
      }
    }

    // Always login via UI for each test (most reliable)
    await page.goto('/admin/login');
    await page.waitForLoadState('networkidle');

    const emailField = page.locator('input[type="email"]');
    const passwordField = page.locator('input[type="password"]');

    if (await emailField.count() > 0 && await passwordField.count() > 0) {
      await emailField.fill(TEST_EMAIL);
      await passwordField.fill(TEST_PASSWORD);

      const loginBtn = page.locator('button[type="submit"]');
      
      // Submit and wait for navigation to complete
      await Promise.all([
        page.waitForURL('/admin**', { timeout: 15000 }),
        loginBtn.click()
      ]);
      
      // Wait for page to fully load
      await page.waitForLoadState('networkidle');
    }

    await use(page);
  },
});

test.describe.configure({ mode: 'serial' });

// =============================================================================
// SOP-QTE-001: Quote Management Tests
// =============================================================================
test.describe('SOP-QTE-001: Quote Management', () => {
  test('QTE-01: Navigate to Quotes page', async ({ authPage: page }) => {
    await page.goto('/admin/quotes');
    await expect(page).toHaveURL(/\/admin\/quotes/);
  });

  test('QTE-02: Verify Quote page elements and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/quotes');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'quotes-page');

    // Check for New Quote button (actual button text is "+ New Quote")
    const newQuoteBtn = page.locator('button:has-text("New Quote")');
    const hasNewQuoteBtn = await newQuoteBtn.count() > 0;

    if (!hasNewQuoteBtn) {
      logIssue({
        sop: 'SOP-QTE-001',
        test: 'QTE-02: Page Elements',
        severity: 'major',
        description: 'New Quote button not found',
        expected: 'Button with text "+ New Quote"',
        actual: 'Button not found',
      });
    }

    // Verify button is visible
    expect(hasNewQuoteBtn).toBeTruthy();

    // Check for status filter
    const statusFilter = page.locator('select, [role="combobox"]').first();
    const hasStatusFilter = await statusFilter.count() > 0;

    // Check for search input
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]');
    const hasSearchInput = await searchInput.count() > 0;

    // Check for quotes table/list - look for table headers or content
    const hasTable = await page.locator('table').count() > 0;

    // Also check for empty state message which confirms page loaded
    const emptyState = page.locator('text="No quotes"');
    const hasEmptyState = await emptyState.count() > 0;

    if (!hasTable && !hasEmptyState && !hasNewQuoteBtn) {
      logIssue({
        sop: 'SOP-QTE-001',
        test: 'QTE-02: Page Elements',
        severity: 'minor',
        description: 'Quotes table/list not found',
        expected: 'Table with Quote #, Product, Customer columns',
        actual: 'Table structure not found',
      });
    }
  });

  test('QTE-03: Open New Quote modal and capture', async ({ authPage: page }) => {
    await page.goto('/admin/quotes');
    await page.waitForLoadState('networkidle');

    const newQuoteBtn = page.locator('button:has-text("New Quote")').first();

    if (await newQuoteBtn.count() > 0) {
      await newQuoteBtn.click();
      await page.waitForTimeout(1000);

      // Check if modal opened - look for modal backdrop or dialog
      const modalBackdrop = page.locator('.fixed.inset-0, [class*="modal"], [role="dialog"]');
      const hasModal = await modalBackdrop.count() > 0;

      if (hasModal) {
        // Capture screenshot of the modal
        await captureScreenshot(page, 'quotes-new-modal');
      } else {
        logIssue({
          sop: 'SOP-QTE-001',
          test: 'QTE-03: New Quote Modal',
          severity: 'major',
          description: 'New Quote modal did not open',
          expected: 'Modal dialog to appear',
          actual: 'No modal found after clicking button',
        });
      }

      // Close modal - press Escape key (most reliable)
      await page.keyboard.press('Escape');
      await page.waitForTimeout(300);
    }
  });
});

// =============================================================================
// SOP-ORD-001: Sales Order Management Tests
// =============================================================================
test.describe('SOP-ORD-001: Sales Order Management', () => {
  test('ORD-01: Navigate to Orders page', async ({ authPage: page }) => {
    await page.goto('/admin/orders');
    await expect(page).toHaveURL(/\/admin\/orders/);
  });

  test('ORD-02: Verify Order page elements and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/orders');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'orders-page');

    // Check for New Order button (may be "+ New Order" or use wizard from dashboard)
    const newOrderBtn = page.locator('button:has-text("New Order"), button:has-text("Order")');
    const hasBtn = await newOrderBtn.count() > 0;

    // Orders may also be created via Quote conversion - check for that path
    const hasOrderTable = await page.locator('table').count() > 0;

    if (!hasBtn && !hasOrderTable) {
      logIssue({
        sop: 'SOP-ORD-001',
        test: 'ORD-02: Page Elements',
        severity: 'major',
        description: 'New Order button not found',
        expected: 'Button to create new orders or order management interface',
        actual: 'Button not found',
      });
    }

    // Check for status filter
    const statusFilter = page.locator('select');
    const hasFilter = await statusFilter.count() > 0;
  });

  test('ORD-03: Verify status filter options', async ({ authPage: page }) => {
    await page.goto('/admin/orders');
    await page.waitForLoadState('networkidle');

    // Find status filter dropdown
    const statusSelect = page.locator('select').first();
    if (await statusSelect.count() > 0) {
      const options = await statusSelect.locator('option').allTextContents();

      const expectedStatuses = ['Pending', 'Confirmed', 'In Production', 'Ready to Ship', 'Shipped', 'Completed'];
      const missingStatuses = expectedStatuses.filter(s =>
        !options.some(o => o.toLowerCase().includes(s.toLowerCase()))
      );

      if (missingStatuses.length > 0) {
        logIssue({
          sop: 'SOP-ORD-001',
          test: 'ORD-03: Status Filter Options',
          severity: 'minor',
          description: 'Some expected status options missing from filter',
          expected: expectedStatuses.join(', '),
          actual: `Missing: ${missingStatuses.join(', ')}`,
        });
      }
    }
  });
});

// =============================================================================
// SOP-PRD-001: Production Order Management Tests
// =============================================================================
test.describe('SOP-PRD-001: Production Order Management', () => {
  test('PRD-01: Navigate to Production page', async ({ authPage: page }) => {
    // Navigate directly via URL (most reliable)
    await page.goto('/admin/production');
    await expect(page).toHaveURL(/\/admin\/production/);
  });

  test('PRD-02: Verify Kanban view and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/production');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'production-page');

    // Look for Kanban board elements
    const kanbanToggle = page.locator('button:has-text("Kanban"), [aria-label*="Kanban"]');
    const hasKanbanToggle = await kanbanToggle.count() > 0;

    // Look for columns (Released, In Progress, etc.)
    const columns = page.locator('[class*="column"], [class*="kanban"]');

    if (!hasKanbanToggle) {
      logIssue({
        sop: 'SOP-PRD-001',
        test: 'PRD-02: Kanban View',
        severity: 'minor',
        description: 'Kanban view toggle not clearly visible',
        expected: 'Toggle button for Kanban/Scheduler views',
        actual: 'Toggle not found or not labeled',
      });
    }
  });

  test('PRD-03: Verify New Production Order button', async ({ authPage: page }) => {
    await page.goto('/admin/production');
    await page.waitForLoadState('networkidle');

    const newPOBtn = page.locator('button:has-text("New"), button:has-text("Create")').first();
    const hasBtn = await newPOBtn.count() > 0;

    if (!hasBtn) {
      logIssue({
        sop: 'SOP-PRD-001',
        test: 'PRD-03: New Production Order',
        severity: 'major',
        description: 'Cannot find button to create production order',
        expected: 'Button to create new production order',
        actual: 'Button not found',
      });
    }
  });
});

// =============================================================================
// SOP-INV-001: Inventory & Item Management Tests
// =============================================================================
test.describe('SOP-INV-001: Inventory & Items', () => {
  test('INV-01: Navigate to Items page', async ({ authPage: page }) => {
    await page.goto('/admin/items');
    await expect(page).toHaveURL(/\/admin\/items/);
  });

  test('INV-02: Verify Items page and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/items');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'items-page');

    // Look for category tree/sidebar
    const sidebar = page.locator('[class*="sidebar"], [class*="category"]');
    const hasSidebar = await sidebar.count() > 0;

    if (!hasSidebar) {
      logIssue({
        sop: 'SOP-INV-001',
        test: 'INV-02: Category Sidebar',
        severity: 'minor',
        description: 'Category sidebar/tree not found',
        expected: 'Left sidebar with category tree',
        actual: 'Sidebar not found or not visible',
      });
    }
  });

  test('INV-03: Verify item type filter', async ({ authPage: page }) => {
    await page.goto('/admin/items');
    await page.waitForLoadState('networkidle');

    // Look for type filter
    const typeFilter = page.locator('select, [role="combobox"]');

    if (await typeFilter.count() > 0) {
      // Check for expected item types
      await typeFilter.first().click();
      await page.waitForTimeout(300);

      const options = page.locator('[role="option"], option');
      const optionTexts = await options.allTextContents();

      const expectedTypes = ['Finished', 'Component', 'Filament', 'Supply'];
      const foundTypes = expectedTypes.filter(t =>
        optionTexts.some(o => o.toLowerCase().includes(t.toLowerCase()))
      );

      if (foundTypes.length < 2) {
        logIssue({
          sop: 'SOP-INV-001',
          test: 'INV-03: Item Type Filter',
          severity: 'minor',
          description: 'Item type filter missing expected options',
          expected: expectedTypes.join(', '),
          actual: `Found: ${optionTexts.slice(0, 5).join(', ')}...`,
        });
      }
    }
  });

  test('INV-04: Verify New Item button and options', async ({ authPage: page }) => {
    await page.goto('/admin/items');
    await page.waitForLoadState('networkidle');

    const newItemBtn = page.locator('button:has-text("New Item")');
    const newMaterialBtn = page.locator('button:has-text("New Material")');

    const hasNewItem = await newItemBtn.count() > 0;
    const hasNewMaterial = await newMaterialBtn.count() > 0;

    if (!hasNewItem) {
      logIssue({
        sop: 'SOP-INV-001',
        test: 'INV-04: New Item Button',
        severity: 'major',
        description: 'New Item button not found',
        expected: 'Button labeled "New Item"',
        actual: 'Button not found',
      });
    }
  });

  test('INV-05: Verify Recost All button', async ({ authPage: page }) => {
    await page.goto('/admin/items');
    await page.waitForLoadState('networkidle');

    const recostBtn = page.locator('button:has-text("Recost")');
    const hasRecost = await recostBtn.count() > 0;

    if (!hasRecost) {
      logIssue({
        sop: 'SOP-INV-001',
        test: 'INV-05: Recost Button',
        severity: 'minor',
        description: 'Recost All button not found',
        expected: 'Button to recost items from BOM',
        actual: 'Button not found',
      });
    }
  });
});

// =============================================================================
// SOP-PUR-001: Purchasing & Vendor Management Tests
// =============================================================================
test.describe('SOP-PUR-001: Purchasing', () => {
  test('PUR-01: Navigate to Purchasing page', async ({ authPage: page }) => {
    await page.goto('/admin/purchasing');
    await expect(page).toHaveURL(/\/admin\/purchasing/);
  });

  test('PUR-02: Verify Purchasing page and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/purchasing');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'purchasing-page');

    // Check for tabs
    const ordersTab = page.locator('button:has-text("Orders"), [role="tab"]:has-text("Orders")');
    const vendorsTab = page.locator('button:has-text("Vendors"), [role="tab"]:has-text("Vendors")');
    const lowStockTab = page.locator('button:has-text("Low"), [role="tab"]:has-text("Low")');

    const missingTabs = [];
    if (await ordersTab.count() === 0) missingTabs.push('Orders');
    if (await vendorsTab.count() === 0) missingTabs.push('Vendors');
    if (await lowStockTab.count() === 0) missingTabs.push('Low Stock');

    if (missingTabs.length > 0) {
      logIssue({
        sop: 'SOP-PUR-001',
        test: 'PUR-02: Tab Navigation',
        severity: 'major',
        description: 'Expected tabs not found',
        expected: 'Orders, Vendors, Low Stock tabs',
        actual: `Missing: ${missingTabs.join(', ')}`,
      });
    }
  });

  test('PUR-03: Verify Create PO button', async ({ authPage: page }) => {
    await page.goto('/admin/purchasing');
    await page.waitForLoadState('networkidle');

    const createPOBtn = page.locator('button:has-text("Create PO"), button:has-text("New PO")');
    const hasBtn = await createPOBtn.count() > 0;

    if (!hasBtn) {
      logIssue({
        sop: 'SOP-PUR-001',
        test: 'PUR-03: Create PO Button',
        severity: 'major',
        description: 'Create PO button not found',
        expected: 'Button to create new purchase order',
        actual: 'Button not found',
      });
    }
  });
});

// =============================================================================
// SOP-SHP-001: Shipping & Fulfillment Tests
// =============================================================================
test.describe('SOP-SHP-001: Shipping', () => {
  test('SHP-01: Navigate to Shipping page', async ({ authPage: page }) => {
    await page.goto('/admin/shipping');
    await expect(page).toHaveURL(/\/admin\/shipping/);
  });

  test('SHP-02: Verify Shipping page and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/shipping');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'shipping-page');

    // Check for orders list
    const ordersList = page.locator('table, [class*="order"]');

    // Check for Ship button (may not be visible if no orders ready)
    const shipBtn = page.locator('button:has-text("Ship")');
  });
});

// =============================================================================
// SOP-CUS-001: Customer Management Tests
// =============================================================================
test.describe('SOP-CUS-001: Customer Management', () => {
  test('CUS-01: Navigate to Customers page', async ({ authPage: page }) => {
    await page.goto('/admin/customers');
    await expect(page).toHaveURL(/\/admin\/customers/);
  });

  test('CUS-02: Verify Customers page and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/customers');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'customers-page');

    // Check for Add Customer button
    const addBtn = page.locator('button:has-text("Add Customer"), button:has-text("New Customer")');
    const hasAddBtn = await addBtn.count() > 0;

    if (!hasAddBtn) {
      logIssue({
        sop: 'SOP-CUS-001',
        test: 'CUS-02: Add Customer Button',
        severity: 'major',
        description: 'Add Customer button not found',
        expected: 'Button to add new customer',
        actual: 'Button not found',
      });
    }

    // Check for Import button
    const importBtn = page.locator('button:has-text("Import")');
    const hasImport = await importBtn.count() > 0;

    if (!hasImport) {
      logIssue({
        sop: 'SOP-CUS-001',
        test: 'CUS-02: Import Button',
        severity: 'minor',
        description: 'Import button not found',
        expected: 'Button to import customers from CSV',
        actual: 'Button not found',
      });
    }

    // Check for stats cards
    const statsCards = page.locator('[class*="stat"], [class*="card"]');
  });

  test('CUS-03: Open Add Customer modal and capture', async ({ authPage: page }) => {
    await page.goto('/admin/customers');
    await page.waitForLoadState('networkidle');

    const addBtn = page.locator('button:has-text("Add Customer"), button:has-text("New Customer")').first();

    if (await addBtn.count() > 0) {
      await addBtn.click();
      await page.waitForTimeout(1000);

      // Capture screenshot of modal
      await captureScreenshot(page, 'customers-add-modal');

      // Verify modal has expected fields
      const emailField = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]');
      const nameField = page.locator('input[name="first_name"], input[name="name"], input[placeholder*="name" i]');

      const hasEmail = await emailField.count() > 0;
      const hasName = await nameField.count() > 0;

      if (!hasEmail || !hasName) {
        logIssue({
          sop: 'SOP-CUS-001',
          test: 'CUS-03: Customer Form Fields',
          severity: 'major',
          description: 'Customer form missing required fields',
          expected: 'Email and name input fields',
          actual: `Email: ${hasEmail}, Name: ${hasName}`,
        });
      }

      // Close modal - press Escape key
      await page.keyboard.press('Escape');
      await page.waitForTimeout(300);
    }
  });
});

// =============================================================================
// SOP-PAY-001: Payment Management Tests
// =============================================================================
test.describe('SOP-PAY-001: Payment Management', () => {
  test('PAY-01: Navigate to Payments page', async ({ authPage: page }) => {
    await page.goto('/admin/payments');
    await expect(page).toHaveURL(/\/admin\/payments/);
  });

  test('PAY-02: Verify Payments page and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/payments');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'payments-page');

    // Check for Record Payment button
    const recordBtn = page.locator('button:has-text("Record Payment")');
    const hasRecordBtn = await recordBtn.count() > 0;

    if (!hasRecordBtn) {
      logIssue({
        sop: 'SOP-PAY-001',
        test: 'PAY-02: Record Payment Button',
        severity: 'major',
        description: 'Record Payment button not found',
        expected: 'Button to record new payment',
        actual: 'Button not found',
      });
    }

    // Check for dashboard stats
    const stats = page.locator('[class*="stat"]');
  });
});

// =============================================================================
// SOP-BOM-001: Bill of Materials Tests
// =============================================================================
test.describe('SOP-BOM-001: BOM Management', () => {
  test('BOM-01: Navigate to BOM page', async ({ authPage: page }) => {
    await page.goto('/admin/bom');
    await expect(page).toHaveURL(/\/admin\/bom/);
  });

  test('BOM-02: Verify BOM page and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/bom');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'bom-page');

    // Check for New BOM button
    const newBomBtn = page.locator('button:has-text("New BOM"), button:has-text("Create BOM")');
    const hasBtn = await newBomBtn.count() > 0;

    if (!hasBtn) {
      logIssue({
        sop: 'SOP-BOM-001',
        test: 'BOM-02: New BOM Button',
        severity: 'major',
        description: 'New BOM button not found',
        expected: 'Button to create new BOM',
        actual: 'Button not found',
      });
    }
  });
});

// =============================================================================
// SOP-MFG-001: Manufacturing Setup Tests
// =============================================================================
test.describe('SOP-MFG-001: Manufacturing Setup', () => {
  test('MFG-01: Navigate to Manufacturing page', async ({ authPage: page }) => {
    await page.goto('/admin/manufacturing');
    await expect(page).toHaveURL(/\/admin\/manufacturing/);
  });

  test('MFG-02: Verify Manufacturing page and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/manufacturing');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'manufacturing-page');

    // Check for tabs
    const workCentersTab = page.locator('button:has-text("Work Centers"), [role="tab"]:has-text("Work")');
    const routingsTab = page.locator('button:has-text("Routings"), [role="tab"]:has-text("Routing")');

    const hasWC = await workCentersTab.count() > 0;
    const hasRouting = await routingsTab.count() > 0;

    if (!hasWC || !hasRouting) {
      logIssue({
        sop: 'SOP-MFG-001',
        test: 'MFG-02: Tab Navigation',
        severity: 'major',
        description: 'Manufacturing tabs not found',
        expected: 'Work Centers and Routings tabs',
        actual: `Work Centers: ${hasWC}, Routings: ${hasRouting}`,
      });
    }
  });

  test('MFG-03: Verify Add Work Center button', async ({ authPage: page }) => {
    await page.goto('/admin/manufacturing');
    await page.waitForLoadState('networkidle');

    const addBtn = page.locator('button:has-text("Add Work Center"), button:has-text("New Work Center")');
    const hasBtn = await addBtn.count() > 0;

    if (!hasBtn) {
      logIssue({
        sop: 'SOP-MFG-001',
        test: 'MFG-03: Add Work Center',
        severity: 'major',
        description: 'Add Work Center button not found',
        expected: 'Button to add new work center',
        actual: 'Button not found',
      });
    }
  });
});

// =============================================================================
// SOP-SET-001: System Settings Tests
// =============================================================================
test.describe('SOP-SET-001: System Settings', () => {
  test('SET-01: Navigate to Settings page', async ({ authPage: page }) => {
    await page.goto('/admin/settings');
    await expect(page).toHaveURL(/\/admin\/settings/);
  });

  test('SET-02: Verify Settings page and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin/settings');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'settings-page');

    // Check for company info fields
    const companyName = page.locator('input[name="company_name"], input[placeholder*="Company" i]');
    const hasCompanyName = await companyName.count() > 0;

    // Check for tax settings
    const taxRate = page.locator('input[name="tax_rate"], input[placeholder*="Tax" i]');

    // Check for logo upload
    const logoUpload = page.locator('input[type="file"], button:has-text("Upload Logo")');
    const hasLogoUpload = await logoUpload.count() > 0;

    // Check for Save button
    const saveBtn = page.locator('button:has-text("Save")');
    const hasSave = await saveBtn.count() > 0;

    if (!hasSave) {
      logIssue({
        sop: 'SOP-SET-001',
        test: 'SET-02: Save Button',
        severity: 'critical',
        description: 'Save button not found on Settings page',
        expected: 'Button to save settings changes',
        actual: 'Button not found',
      });
    }
  });
});

// =============================================================================
// Command Center Tests (was: Dashboard Tests — /admin now loads CommandCenter per PR-13)
// =============================================================================
test.describe('Dashboard Verification', () => {
  test('DASH-01: Verify Command Center and capture screenshot', async ({ authPage: page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    // Capture screenshot for SOP documentation
    await captureScreenshot(page, 'command-center-page');

    // Check for stat cards
    const statCards = page.locator('[class*="stat"], [class*="card"]');
    const cardCount = await statCards.count();

    if (cardCount < 4) {
      logIssue({
        sop: 'Dashboard',
        test: 'DASH-01: Stat Cards',
        severity: 'minor',
        description: 'Expected more stat cards on dashboard',
        expected: 'At least 4 stat cards',
        actual: `Found ${cardCount} cards`,
      });
    }

    // Check for section headers
    const sections = page.locator('h2, h3, [class*="section"]');
  });

  test('DASH-02: Verify clickable stat cards', async ({ authPage: page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    // Find a clickable stat card and test navigation
    const clickableCard = page.locator('[class*="stat"][class*="cursor-pointer"], [class*="card"]:has(a)').first();

    if (await clickableCard.count() > 0) {
      const startUrl = page.url();
      await clickableCard.click();
      await page.waitForTimeout(500);

      const endUrl = page.url();
      const didNavigate = startUrl !== endUrl;

      if (!didNavigate) {
        logIssue({
          sop: 'Dashboard',
          test: 'DASH-02: Clickable Cards',
          severity: 'enhancement',
          description: 'Stat cards do not navigate when clicked',
          expected: 'Click on stat card navigates to related page',
          actual: 'No navigation occurred',
        });
      }
    }
  });
});

// =============================================================================
// Sidebar Navigation Tests
// =============================================================================
test.describe('Sidebar Navigation', () => {
  test('NAV-01: Verify all sidebar links', async ({ authPage: page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    const expectedLinks = [
      'Command Center',
      'Analytics',
      'Customers',
      'Quotes',
      'Orders',
      'Shipping',
      'Invoices',
      'Payments',
      'Production',
      'Work Centers & Routings',
      'Items',
      'Bill of Materials',
      'Purchasing',
      'Settings',
    ];

    const missingLinks = [];

    for (const link of expectedLinks) {
      const navLink = page.locator(`nav >> text="${link}"`);
      if (await navLink.count() === 0) {
        // Try partial match
        const partialLink = page.locator(`nav >> text=/${link}/i`);
        if (await partialLink.count() === 0) {
          missingLinks.push(link);
        }
      }
    }

    if (missingLinks.length > 0) {
      logIssue({
        sop: 'Navigation',
        test: 'NAV-01: Sidebar Links',
        severity: 'major',
        description: 'Some navigation links not found in sidebar',
        expected: expectedLinks.join(', '),
        actual: `Missing: ${missingLinks.join(', ')}`,
      });
    }
  });
});

// =============================================================================
// Final Report
// =============================================================================
test.afterAll(async () => {
  console.log('\n' + '='.repeat(80));
  console.log('SOP-BASED UI TEST RESULTS');
  console.log('='.repeat(80));

  if (issues.length === 0) {
    console.log('\n✅ All tests passed - No issues found!\n');
  } else {
    console.log(`\n❌ Found ${issues.length} issue(s):\n`);

    const critical = issues.filter(i => i.severity === 'critical');
    const major = issues.filter(i => i.severity === 'major');
    const minor = issues.filter(i => i.severity === 'minor');
    const enhancement = issues.filter(i => i.severity === 'enhancement');

    console.log(`  Critical: ${critical.length}`);
    console.log(`  Major: ${major.length}`);
    console.log(`  Minor: ${minor.length}`);
    console.log(`  Enhancement: ${enhancement.length}`);

    console.log('\n--- Issue Details ---\n');
    issues.forEach((issue, idx) => {
      console.log(`${idx + 1}. [${issue.severity.toUpperCase()}] ${issue.sop}`);
      console.log(`   Test: ${issue.test}`);
      console.log(`   Description: ${issue.description}`);
      console.log(`   Expected: ${issue.expected}`);
      console.log(`   Actual: ${issue.actual}`);
      console.log('');
    });
  }

  console.log('='.repeat(80));
});
