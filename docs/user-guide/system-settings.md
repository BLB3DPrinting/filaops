# System Settings

> Configure your company profile, tax rules, inventory locations, and production settings.

## What You'll Learn

- How to set up your company information and logo
- How to configure sales tax
- How to customize quote defaults and business hours
- How to organize inventory with locations
- How to define scrap reasons for production tracking

## Prerequisites

- Admin access to FilaOps

---

## Company Settings

Navigate to **Settings > Company Settings** in the sidebar. This is the central configuration page for your business profile.

<!-- TODO: screenshot of company settings page -->

### Company Logo

Your logo appears on quotes, invoices, and the login page.

**To upload a logo:**

**Step 1.** Click **Upload Logo** (or **Change Logo** if one is already set).

**Step 2.** Select an image file. Supported formats: PNG, JPEG, GIF, or WebP. Maximum file size: 2 MB.

**Step 3.** The logo appears immediately in the preview area.

**To remove a logo:** Click the red **X** button on the preview to delete it.

### Company Information

Fill in your business details. These appear on customer-facing documents like quotes and invoices.

| Field | Notes |
|-------|-------|
| **Company Name** | Your business name as it should appear on documents |
| **Address Line 1** | Street address |
| **Address Line 2** | Suite, unit, or building (optional) |
| **City** | City name |
| **State** | State or province abbreviation |
| **ZIP Code** | Postal code |
| **Country** | Country name (defaults to "USA") |
| **Timezone** | Your local timezone for date/time display (defaults to "America/New_York") |
| **Phone** | Business phone number — automatically formatted as (555) 123-4567 |
| **Email** | Business contact email |
| **Website URL** | Your website address (optional) |

### Tax Settings

Control whether FilaOps calculates sales tax on quotes and orders.

**Step 1.** Check **Enable sales tax on quotes** to turn on tax calculation.

**Step 2.** Configure the tax details:

| Field | Notes |
|-------|-------|
| **Tax Rate** | Percentage from 0 to 100, supports decimals (e.g., 8.25) |
| **Tax Name** | Label shown on documents (defaults to "Sales Tax") |
| **Tax Registration Number** | Your sales tax permit or registration number (optional, shown on documents) |

!!! warning "Tax on existing orders"
    Changing the tax rate only affects new orders. Existing orders keep the tax rate that was in effect when they were created.

### Quote Settings

Customize the default values for new quotes.

| Field | Notes |
|-------|-------|
| **Default Quote Validity** | Number of days a quote is valid (1–365, defaults to 30) |
| **Quote Terms and Conditions** | Text that appears on all quotes — payment terms, delivery policy, etc. |
| **Quote Footer Message** | Additional text at the bottom of quotes — thank you message, disclaimers, etc. |

### Business Hours

Define your standard operating hours. These are used for scheduling calculations in production planning.

| Field | Notes |
|-------|-------|
| **Start Time Hour** | Hour the workday begins (0–23, defaults to 8 for 8:00 AM) |
| **End Time Hour** | Hour the workday ends (0–23, defaults to 16 for 4:00 PM) |
| **Days Per Week** | Working days per week (1–7, defaults to 5) |
| **Work Days** | Comma-separated list of working days where 0=Monday through 6=Sunday (defaults to "0,1,2,3,4" for Monday–Friday) |

!!! tip "24-hour print farms"
    If your printers run longer than standard business hours, set the start and end times to reflect your actual operating window. For example, a farm running 4:00 AM to midnight would use Start=4, End=24.

### Version and Updates

At the bottom of the settings page, you can see:

- **Current Version** — The version of FilaOps you're running
- **Latest Version** — The most recent release available
- **Check for Updates** — Click to check if a newer version is available
- **View Release Notes** — Opens the changelog for the latest release

### Saving

Click **Save Settings** at the bottom of the page to apply all changes. Changes take effect immediately.

---

## Inventory Locations

Navigate to **Settings > Locations** in the sidebar to organize your physical storage spaces.

<!-- TODO: screenshot of locations page -->

### Why Use Locations?

Locations help you track where inventory is physically stored. When you receive materials or move stock, you can specify the location. This is especially useful for farms with multiple storage areas, shelves, or staging zones.

### Location Types

| Type | Color | Typical Use |
|------|-------|------------|
| **Warehouse** | Blue | A main storage building or room |
| **Shelf** | Green | A shelf or rack within a warehouse |
| **Bin** | Orange | A specific bin or container on a shelf |
| **Staging Area** | Purple | A temporary holding area for work-in-progress |
| **Quality/QC** | Orange | An area for quality inspection or quarantine |

### Viewing Locations

The table shows all locations with their **Code** (monospace), **Name**, **Type** (color-coded badge), **Parent** location (if nested), and **Status** (Active or Inactive).

Check **Show inactive locations** to include deactivated locations in the list.

### Creating a Location

**Step 1.** Click **+ Add Location**.

**Step 2.** Fill in the fields:

| Field | Required | Notes |
|-------|----------|-------|
| **Code** | Yes | Short identifier, automatically converted to uppercase (e.g., "SHELF-A1") |
| **Name** | Yes | Descriptive name (e.g., "Main Shelf Row A, Bin 1") |
| **Type** | Yes | Select from the location types above |
| **Parent Location** | No | Nest this location under another (e.g., a shelf under a warehouse) |

**Step 3.** Click **Create**.

### Organizing with Parent Locations

Locations can be nested to reflect your physical layout:

```
Warehouse: MAIN
├── Shelf: SHELF-A
│   ├── Bin: BIN-A1
│   └── Bin: BIN-A2
├── Shelf: SHELF-B
└── Staging Area: STAGING
```

When creating a location, select a **Parent Location** to nest it. The parent's code appears in the table for easy reference.

### Editing and Deactivating

- Click the **Edit** (pencil) button to update a location's name, type, or parent.
- Click the **Delete** (trash) button to deactivate a location. Deactivated locations are hidden by default but preserved for historical records.
- The **MAIN** location cannot be deleted — it's the system default.
- Click the **Reactivate** (refresh) button on an inactive location to bring it back.

---

## Scrap Reasons

Navigate to **Settings > Scrap Reasons** in the sidebar to define the failure modes tracked when scrapping production orders.

<!-- TODO: screenshot of scrap reasons page -->

### What Are Scrap Reasons?

When a production order fails and material must be scrapped, FilaOps asks for a reason. These reasons help you identify recurring problems and improve your processes over time. Common examples: print failure, material defect, operator error, equipment malfunction.

### Viewing Scrap Reasons

The table shows each reason with its **Order** (sort sequence), **Code**, **Name**, **Description**, and **Status** (Active or Inactive).

### Creating a Scrap Reason

**Step 1.** Click **+ Add Scrap Reason**.

**Step 2.** Fill in the fields:

| Field | Required | Notes |
|-------|----------|-------|
| **Code** | Yes | Short identifier using lowercase letters and underscores (e.g., "print_failure"). Cannot be changed after creation. |
| **Name** | Yes | Display name shown in the scrap dropdown (e.g., "Print Failure") |
| **Description** | No | Longer explanation of when to use this reason |
| **Sort Order** | No | Lower numbers appear first in the dropdown (defaults to 0) |

**Step 3.** Click **Create**.

### Editing and Toggling

- Click the **Edit** (pencil) button to change the name, description, or sort order. The code cannot be changed after creation.
- Click the **X** button to deactivate a reason, or the **checkmark** button to reactivate it. Inactive reasons don't appear in the scrap dropdown.

---

## Price Levels

Navigate to **Admin > Price Levels** in the sidebar to define wholesale pricing tiers for your business.

<!-- TODO: screenshot of price levels page -->

### What Are Price Levels?

Price levels let you offer different discount percentages to different customer groups — for example, "Tier A — 25% off" for high-volume buyers or "Reseller — 15% off" for distribution partners. You define the tiers here in Core; assigning specific customers to a price level is a [FilaOps PRO](https://blb3dprinting.com) feature.

### Viewing Price Levels

The table shows each level with its **Name**, **Discount %**, **Description**, and **Status** (Active or Inactive).

### Creating a Price Level

**Step 1.** Click **+ Add Price Level**.

**Step 2.** Fill in the fields:

| Field | Required | Notes |
|-------|----------|-------|
| **Name** | Yes | Unique display name (e.g., "Tier A", "Wholesale") |
| **Discount %** | Yes | Percentage off list price — 0 to 100 |
| **Description** | No | Notes about who qualifies for this tier |

**Step 3.** Click **Save**.

### Editing and Managing Price Levels

- Click the **Edit** (pencil) button to update a level's name, discount, or description.
- Click the **Delete** button to deactivate a level. Deactivated levels are hidden from the active list but preserved for historical records.

---

## Tips and Best Practices

- **Complete your company info first** — This information appears on quotes and invoices. Fill it in during initial setup before sending your first quote.
- **Set up locations before receiving inventory** — Define at least your main storage areas so you can track where materials go from day one.
- **Use descriptive location codes** — Codes like "WH-A-SHELF-3" are easier to work with than "LOC001". Keep them short but meaningful.
- **Start with a few scrap reasons** — You can always add more later as you identify new failure modes. Common starting set: print failure, material defect, wrong settings, equipment fault.
- **Review settings after updates** — New FilaOps versions may add settings. Check the company settings page after each update.

## What's Next?

- [Your First Day](first-day.md) — initial setup walkthrough that references these settings
- [Managing Your Product Catalog](product-catalog.md) — products and BOMs that reference locations
- [Tracking Inventory](inventory.md) — using locations for stock management
- [Running Production](production.md) — scrap reasons in the production workflow
- [Basic Accounting](accounting.md) — tax settings affect accounting reports

## Quick Reference

| Task | Where to Find It |
|------|-------------------|
| Edit company name and address | **Settings** > **Company Settings** > Company Information |
| Upload company logo | **Settings** > **Company Settings** > Company Logo |
| Configure sales tax | **Settings** > **Company Settings** > Tax Settings |
| Set quote defaults | **Settings** > **Company Settings** > Quote Settings |
| Set business hours | **Settings** > **Company Settings** > Business Hours |
| Check for updates | **Settings** > **Company Settings** > Version & Updates |
| Manage inventory locations | **Settings** > **Locations** |
| Add a storage location | **Settings** > **Locations** > **+ Add Location** |
| Configure scrap reasons | **Settings** > **Scrap Reasons** |
| Add a scrap reason | **Settings** > **Scrap Reasons** > **+ Add Scrap Reason** |
| Manage price levels | **Admin** > **Price Levels** |
| Add a price level | **Admin** > **Price Levels** > **+ Add Price Level** |
