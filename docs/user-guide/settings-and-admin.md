# Settings & Administration

## Overview

The Settings & Administration module is your control center for configuring FilaOps. From company branding and tax settings to user management, work centers, and system updates, this guide covers everything you need to manage your FilaOps installation.

**What This Module Covers:**
- **Company Settings** - Name, address, logo, tax configuration
- **User Management** - Creating admin/operator accounts, roles, password resets
- **Locations** - Warehouses, bins, and stock location hierarchy
- **Materials & Colors** - Filament types, color definitions, and inventory
- **Work Centers** - Production areas, costing rates, and capacity
- **Printers** - Multi-brand printer registration, discovery, and monitoring
- **AI Configuration** - Anthropic or Ollama integration for AI features
- **System Administration** - Version info, updates, and dashboard

**Who Uses This Module:**
- **Administrators** - Full access to all settings
- **Operators** - Access to operational settings (printers, work centers)
- **Note:** Customer accounts cannot access admin settings

---

## Table of Contents

1. [Company Settings](#1-company-settings)
2. [User Management](#2-user-management)
3. [Roles and Permissions](#3-roles-and-permissions)
4. [Location Management](#4-location-management)
5. [Material Types and Colors](#5-material-types-and-colors)
6. [Work Centers](#6-work-centers)
7. [Printer Management](#7-printer-management)
8. [AI Configuration](#8-ai-configuration)
9. [Accounting Settings](#9-accounting-settings)
10. [Admin Dashboard](#10-admin-dashboard)
11. [System Administration](#11-system-administration)
12. [Data Import and Export](#12-data-import-and-export)
13. [Troubleshooting](#13-troubleshooting)
14. [Quick Reference](#14-quick-reference)

---

## 1. Company Settings

### 1.1 Company Information

**Navigation:** Settings → **Company**

Configure your business identity that appears on quotes, invoices, and reports.

**Fields:**

| Field | Description | Example |
|-------|-------------|---------|
| **Company Name** | Legal business name | "Acme 3D Printing LLC" |
| **Address Line 1** | Street address | "123 Innovation Blvd" |
| **Address Line 2** | Suite/Unit (optional) | "Suite 200" |
| **City** | City | "Austin" |
| **State** | State/Province | "TX" |
| **ZIP** | Postal code | "78701" |
| **Country** | Country code | "US" |
| **Phone** | Business phone | "(512) 555-0123" |
| **Email** | Business email | "info@acme3d.com" |
| **Website** | Company URL | "https://acme3d.com" |

**To Update:**
1. Navigate to Settings → Company
2. Edit any fields
3. Click **Save**

### 1.2 Company Logo

**Navigation:** Settings → Company → **Logo**

Upload your company logo for use on quotes, invoices, and the application header.

**Supported Formats:**
- PNG (recommended for transparency)
- JPEG/JPG
- GIF
- WebP

**Constraints:**
- Maximum file size: **2 MB**
- Recommended dimensions: 200-400px wide

**To Upload:**
1. Navigate to Settings → Company
2. Click **Upload Logo**
3. Select image file
4. Preview the logo
5. Click **Save**

**To Remove:**
1. Navigate to Settings → Company
2. Click **Delete Logo**

The logo is stored directly in the database (not on the filesystem), so it persists across deployments.

### 1.3 Tax Configuration

**Navigation:** Settings → Company → **Tax**

Configure sales tax for quotes and invoices.

**Fields:**

| Field | Description | Example |
|-------|-------------|---------|
| **Tax Enabled** | Enable/disable tax calculation | Yes |
| **Tax Rate** | Decimal rate (not percentage) | 0.0825 (= 8.25%) |
| **Tax Name** | Display label | "Sales Tax" or "VAT" |
| **Tax Registration Number** | Tax ID or VAT number | "XX-1234567" |

**Examples:**

| Location | Tax Name | Rate (decimal) | Rate (%) |
|----------|----------|----------------|----------|
| Texas, US | Sales Tax | 0.0825 | 8.25% |
| California, US | Sales Tax | 0.0725 | 7.25% |
| UK | VAT | 0.20 | 20% |
| No tax | N/A | 0 | 0% |

**To Configure:**
1. Set **Tax Enabled** to Yes
2. Enter tax rate as a decimal (e.g., 0.0825 for 8.25%)
3. Set the display name
4. Enter your tax registration number
5. Click **Save**

---

## 2. User Management

### 2.1 Understanding User Types

FilaOps has three account types:

| Type | Access Level | Purpose |
|------|-------------|---------|
| **Admin** | Full access to everything | Business owner, IT administrator |
| **Operator** | Operational features only | Production staff, warehouse team |
| **Customer** | Portal access only | External customers (if portal enabled) |

**Note:** The Community tier supports a limited number of admin/operator accounts. See your tier limits in Settings → System.

### 2.2 Creating Users

**Navigation:** Settings → **Users** → **+ New User**

**Required Fields:**
- **Email** - Must be unique, used for login
- **Password** - Minimum 8 characters
- **First Name** - User's first name
- **Last Name** - User's last name
- **Role** - Admin or Operator

**Optional Fields:**
- **Company Name** - If user represents an external org
- **Phone** - Contact number

**Steps:**
1. Click **+ New User**
2. Fill in email, name, and password
3. Select role (Admin or Operator)
4. Click **Create User**

The new user can immediately log in with their credentials.

### 2.3 Managing Existing Users

**Navigation:** Settings → **Users**

**User List Shows:**
- Name and email
- Role (admin/operator)
- Status (active/inactive/suspended)
- Last login date
- Date created

**Actions Available:**

| Action | Description |
|--------|-------------|
| **Edit** | Change name, email, or role |
| **Reset Password** | Set a new password for the user |
| **Deactivate** | Disable login (soft delete) |
| **Reactivate** | Re-enable a deactivated account |

### 2.4 Editing a User

**Navigation:** Settings → Users → (click user) → **Edit**

**Editable Fields:**
- Email address
- First name, last name
- Role (admin ↔ operator)
- Status (active/inactive)

**Safety Rules:**
- You **cannot** demote yourself (admin → operator)
- You **cannot** deactivate yourself
- You **cannot** remove the last admin (at least one admin must exist)

### 2.5 Password Resets

**Admin-Initiated Reset:**
1. Navigate to Settings → Users
2. Click on the user
3. Click **Reset Password**
4. Enter new password
5. Click **Confirm**

**What Happens:**
- Password is immediately changed
- All existing refresh tokens for this user are revoked
- User must log in again with new password

### 2.6 Deactivating and Reactivating Users

**To Deactivate:**
1. Settings → Users → Select user
2. Click **Deactivate**
3. Confirm

**Effect:** User can no longer log in. Their data is preserved (orders, audit trail, etc.).

**To Reactivate:**
1. Settings → Users → Filter: Inactive
2. Select deactivated user
3. Click **Reactivate**
4. User can log in again

### 2.7 User Dashboard Stats

**Navigation:** Settings → Users → **Stats**

View summary information:
- Total admin accounts
- Total operator accounts
- Inactive accounts
- Accounts created this month

---

## 3. Roles and Permissions

### 3.1 Role Comparison

| Feature | Admin | Operator | Customer |
|---------|-------|----------|----------|
| **Dashboard** | Full | Limited | No |
| **Company Settings** | Edit | View | No |
| **User Management** | Full | No | No |
| **Inventory** | Full | Full | No |
| **Production Orders** | Full | Full | No |
| **Sales Orders** | Full | Full | No |
| **Purchasing** | Full | View | No |
| **MRP** | Full | View | No |
| **Accounting** | Full | No | No |
| **Printers** | Full | Full | No |
| **AI Settings** | Full | No | No |
| **System Updates** | Full | No | No |
| **Own Profile** | Edit | Edit | Edit |

### 3.2 When to Use Each Role

**Use Admin for:**
- Business owners
- IT administrators
- Finance/accounting staff
- Anyone who needs full system access

**Use Operator for:**
- Production floor workers
- Warehouse/shipping staff
- Quality control inspectors
- Anyone who needs operational access but not configuration

---

## 4. Location Management

### 4.1 Understanding Locations

Locations represent physical places where inventory is stored. FilaOps supports a hierarchical location structure.

**Location Hierarchy Example:**
```
Main Warehouse (warehouse)
├── Filament Storage (rack)
│   ├── Shelf A - PLA (bin)
│   ├── Shelf B - PETG (bin)
│   └── Shelf C - Specialty (bin)
├── Hardware Zone (rack)
│   ├── Bin 1 - Fasteners (bin)
│   └── Bin 2 - Electronics (bin)
├── Finished Goods (rack)
└── Shipping Area (station)
```

### 4.2 Location Types

| Type | Description | Example |
|------|-------------|---------|
| **Warehouse** | Top-level facility | "Main Warehouse" |
| **Rack** | Section within warehouse | "Filament Storage" |
| **Bin** | Individual storage slot | "Shelf A - PLA" |
| **Station** | Work or staging area | "Shipping Area" |

### 4.3 Creating Locations

**Navigation:** Settings → **Locations** → **+ New Location**

**Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| **Code** | Yes | Unique location code (e.g., "WH-01", "BIN-A1") |
| **Name** | Yes | Human-readable name |
| **Type** | Yes | warehouse, rack, bin, station |
| **Parent** | No | Parent location (for hierarchy) |

**Steps:**
1. Click **+ New Location**
2. Enter code and name
3. Select type
4. Optionally select parent location
5. Click **Create**

### 4.4 Managing Locations

**Edit:** Change name, type, or parent relationship
**Deactivate:** Soft-delete (hides from selection but preserves history)

**Best Practices:**
- Create a default location before adding inventory
- Use consistent code patterns (WH-01, RACK-A, BIN-A1)
- Keep hierarchy shallow (2-3 levels)
- Deactivate rather than delete (preserves transaction history)

---

## 5. Material Types and Colors

### 5.1 Understanding Material Management

FilaOps has a three-level material system designed for 3D printing:

```
Material Type (e.g., PLA)
├── Color (e.g., Black)
│   └── Material-Color Combo (PLA Black)
│       └── Material Inventory (stock tracking)
├── Color (e.g., White)
│   └── Material-Color Combo (PLA White)
└── Color (e.g., Red)
    └── Material-Color Combo (PLA Red)
```

### 5.2 Material Types

**Navigation:** Settings → **Materials** → **Types**

**Material Type Fields:**

| Field | Description | Example |
|-------|-------------|---------|
| **Code** | Unique material code | "PLA" |
| **Name** | Display name | "PLA (Polylactic Acid)" |
| **Base Material** | Material class | PLA, PETG, ABS, ASA, TPU |
| **Process Type** | Manufacturing process | FDM, RESIN, SLS |
| **Density** | Material density (g/cm3) | 1.24 |
| **Requires Enclosure** | Needs enclosed printer | No (PLA), Yes (ABS) |

**Print Settings (per material):**
- Nozzle Temperature: min/max (e.g., 190-220 C for PLA)
- Bed Temperature: min/max (e.g., 50-60 C)
- Volumetric Flow Limit (mm3/s)

**Pricing:**
- Base price per KG
- Price multiplier (for premium variants)

**Visibility:**
- Active / Inactive
- Customer Visible (for portal display)
- Display Order (sort priority)

**Common Material Types (seeded):**

| Code | Base Material | Process | Enclosure | Typical Temp |
|------|--------------|---------|-----------|-------------|
| PLA | PLA | FDM | No | 190-220 C |
| PLA+ | PLA | FDM | No | 200-230 C |
| PETG | PETG | FDM | No | 220-250 C |
| ABS | ABS | FDM | Yes | 230-260 C |
| ASA | ASA | FDM | Yes | 240-260 C |
| TPU | TPU | FDM | No | 210-230 C |

### 5.3 Colors

**Navigation:** Settings → **Materials** → **Colors**

**Color Fields:**

| Field | Description | Example |
|-------|-------------|---------|
| **Code** | Unique color code | "BLK" |
| **Name** | Display name | "Black" |
| **Hex Code** | Primary color (for UI) | "#000000" |
| **Hex Code Secondary** | Secondary (dual-color) | "#333333" |
| **Active** | Available for use | Yes |
| **Customer Visible** | Shown in portal | Yes |
| **Display Order** | Sort priority | 1 |

### 5.4 Material-Color Combinations

Link colors to material types to define which combinations are available.

**Example:** PLA comes in 12 colors, but specialty TPU only comes in 3 colors.

**To Add a Color to a Material:**
1. Navigate to Settings → Materials → Types
2. Select material type (e.g., PLA)
3. Go to **Colors** tab
4. Click **+ Add Color**
5. Select color (e.g., Red)
6. Set display order and visibility
7. Save

### 5.5 Bulk Import Materials

**Navigation:** Settings → Materials → **Import**

**Steps:**
1. Click **Download Template** to get CSV format
2. Fill in material data in CSV
3. Upload CSV file
4. Options:
   - **Update Existing** - Override matching records
   - **Import Categories** - Which categories to import
5. Click **Import**
6. Review results (created, updated, skipped, errors)

---

## 6. Work Centers

### 6.1 Understanding Work Centers

Work centers represent **logical production areas** in your facility. They define where work happens and how much it costs.

**Typical 3D Print Farm Work Centers:**

| Code | Name | Type | Purpose |
|------|------|------|---------|
| FDM-POOL | FDM Printer Pool | machine | 3D printing operations |
| ASSEMBLY | Assembly Station | station | Part assembly and finishing |
| QC | Quality Control | station | Inspection and testing |
| SHIPPING | Shipping Station | station | Packing and label creation |
| FINISHING | Finishing Station | station | Sanding, painting, etc. |

### 6.2 Creating Work Centers

**Navigation:** Settings → **Work Centers** → **+ New Work Center**

**Fields:**

| Field | Description | Example |
|-------|-------------|---------|
| **Code** | Unique identifier | "FDM-POOL" |
| **Name** | Display name | "FDM Printer Pool" |
| **Description** | Details | "All FDM printers for production" |
| **Type** | Category | machine, station, production |
| **Active** | Available for use | Yes |

### 6.3 Work Center Costing

**Navigation:** Settings → Work Centers → (select) → **Costing**

Work centers have three cost rates that combine to calculate total hourly cost:

| Rate | Description | Example |
|------|-------------|---------|
| **Machine Rate ($/hr)** | Equipment depreciation, power, maintenance | $1.50/hr |
| **Labor Rate ($/hr)** | Operator wages allocated to this center | $25.00/hr |
| **Overhead Rate ($/hr)** | Facility costs, supervision, utilities | $5.00/hr |

**Total Hourly Rate** = Machine + Labor + Overhead = $31.50/hr

**How This Is Used:**
- Production orders calculate manufacturing cost using routing operations
- Each routing operation references a work center
- Operation cost = (setup_time + run_time) x work center hourly rate

### 6.4 Work Center Capacity

**Navigation:** Settings → Work Centers → (select) → **Capacity**

| Field | Description | Example |
|-------|-------------|---------|
| **Hours Per Day** | Operating hours | 16 hrs (two shifts) |
| **Units Per Hour** | Throughput rate | 2 parts/hr |
| **Is Bottleneck** | Constrains production | Yes (for printing) |
| **Scheduling Priority** | 1-10 (higher = sooner) | 8 |

**Capacity Planning:**
- MRP and scheduling use capacity to plan realistic timelines
- Bottleneck work centers get priority in scheduling
- Over-capacity warnings highlight when you need more printers/staff

### 6.5 Resources (Machines in Work Centers)

Each work center can contain multiple **resources** (individual machines).

**Example:**
```
FDM-POOL (Work Center)
├── P1X-001 (Bambu Lab P1S)
├── P1X-002 (Bambu Lab P1S)
├── A1M-001 (Bambu Lab A1 Mini)
└── A1M-002 (Bambu Lab A1 Mini)
```

**To Add a Resource:**
1. Navigate to Settings → Work Centers → (select work center)
2. Go to **Resources** tab
3. Click **+ Add Resource**
4. Enter code, name, machine type
5. Optionally link Bambu device ID and IP address
6. Set capacity hours per day
7. Save

---

## 7. Printer Management

### 7.1 Supported Printer Brands

FilaOps supports multiple 3D printer brands:

| Brand | Connection | Features |
|-------|-----------|----------|
| **Bambu Lab** | MQTT / LAN | Full monitoring, AMS support, camera |
| **Klipper** | HTTP API | Print status, temperatures |
| **OctoPrint** | REST API | Print status, webcam |
| **Prusa** | PrusaLink | Basic monitoring |
| **Creality** | Network | Basic monitoring |
| **Generic** | Manual | Manual status updates only |

### 7.2 Adding Printers

**Navigation:** Settings → **Printers** → **+ New Printer**

**Required Fields:**
- **Code** - Unique printer ID (auto-generated if blank)
- **Name** - Human-readable name (e.g., "Printer 1 - P1S")
- **Brand** - Manufacturer (bambulab, klipper, etc.)
- **Model** - Printer model (e.g., "P1S", "X1C")

**Optional Fields:**
- **Serial Number** - For tracking and warranty
- **IP Address** - Network address for monitoring
- **MQTT Topic** - For Bambu Lab MQTT integration
- **Work Center** - Which production area this printer belongs to
- **Location** - Physical location description
- **Notes** - Additional information

### 7.3 Printer Capabilities

When adding a printer, configure its capabilities:

| Capability | Description | Example |
|------------|-------------|---------|
| **Bed Size** | Print volume | "256x256x256" |
| **Heated Bed** | Has heated bed | Yes |
| **Enclosure** | Enclosed chamber | Yes (for ABS/ASA) |
| **AMS Slots** | Auto Material System slots | 4 |
| **Camera** | Has built-in camera | Yes |
| **Max Temp** | Maximum nozzle temperature | 300 C |

These capabilities are stored as flexible JSON, so custom properties can be added.

### 7.4 Printer Discovery

**Navigation:** Settings → Printers → **Discover**

FilaOps can automatically find printers on your network:

**Bambu Lab Discovery:**
1. Click **Discover**
2. Select "Bambu Lab"
3. FilaOps scans the local network
4. Found printers appear in list
5. Click **Add** to register each printer

**Klipper/OctoPrint Discovery:**
1. Click **Discover**
2. Enter IP range to scan
3. Found instances appear
4. Click **Add** to register

### 7.5 Bulk Import Printers

**Navigation:** Settings → Printers → **Import**

Import multiple printers from a CSV file:
1. Download CSV template
2. Fill in printer details
3. Upload CSV
4. Review and confirm import

### 7.6 Printer Status

Printers have the following status values:

| Status | Meaning | Color |
|--------|---------|-------|
| **Idle** | Ready, no current job | Green |
| **Printing** | Actively printing | Blue |
| **Paused** | Print paused | Yellow |
| **Error** | Error state | Red |
| **Maintenance** | Under maintenance | Orange |
| **Offline** | Not responding | Gray |

**Online Detection:** A printer is considered online if it was last seen within 5 minutes.

### 7.7 Testing Printer Connection

**Navigation:** Settings → Printers → (select) → **Test Connection**

Tests network connectivity and API access to the printer. Useful for:
- Verifying IP address is correct
- Checking firewall/network settings
- Confirming API keys/credentials work

---

## 8. AI Configuration

### 8.1 AI Provider Options

FilaOps supports two AI providers:

| Provider | Type | Best For |
|----------|------|----------|
| **Anthropic** (Claude) | Cloud API | Highest quality, requires internet |
| **Ollama** | Local/Self-hosted | Privacy, offline use, no API costs |

### 8.2 Configuring Anthropic

**Navigation:** Settings → **AI** → Provider: Anthropic

**Fields:**
- **API Key** - Your Anthropic API key (starts with `sk-ant-`)
- **Model** - Which Claude model to use (default: claude-sonnet-4-20250514)

**Steps:**
1. Get an API key from [console.anthropic.com](https://console.anthropic.com)
2. Navigate to Settings → AI
3. Select Provider: **Anthropic**
4. Enter your API key
5. Select model
6. Click **Test Connection** to verify
7. Click **Save**

**Security:** API keys are masked in the UI (displayed as `sk-...XYZ`). The full key is stored in the database.

### 8.3 Configuring Ollama

**Navigation:** Settings → **AI** → Provider: Ollama

**Fields:**
- **Ollama URL** - Server address (default: http://localhost:11434)
- **Model** - Which model to use (default: llama3.2)

**Steps:**
1. Install Ollama on your server
2. Pull a model: `ollama pull llama3.2`
3. Navigate to Settings → AI
4. Select Provider: **Ollama**
5. Enter Ollama URL
6. Select model
7. Click **Test Connection** to verify
8. Click **Save**

**Start Ollama:** If Ollama is installed but not running, use the **Start Ollama** button to attempt to start the service.

### 8.4 Blocking External AI

**Navigation:** Settings → AI → **External AI Blocked**

If enabled, forces all AI features to use local-only (Ollama) processing. No data is sent to external APIs.

**Use When:**
- Handling sensitive business data
- Operating in air-gapped environments
- Company policy prohibits external AI services

---

## 9. Accounting Settings

### 9.1 Fiscal Year

**Navigation:** Settings → Company → **Accounting**

| Field | Description | Default |
|-------|-------------|---------|
| **Fiscal Year Start** | Month fiscal year begins | 1 (January) |
| **Accounting Method** | Cash or Accrual | Accrual |
| **Currency Code** | Base currency | USD |

**Common Fiscal Year Starts:**
- January (1) - Calendar year (most common)
- April (4) - UK tax year
- July (7) - Australian financial year
- October (10) - US federal government

### 9.2 Business Hours

**Navigation:** Settings → Company → **Schedule**

| Field | Description | Default |
|-------|-------------|---------|
| **Timezone** | IANA timezone | America/New_York |
| **Business Hours Start** | Opening hour (0-23) | 8 (8:00 AM) |
| **Business Hours End** | Closing hour (0-23) | 16 (4:00 PM) |
| **Business Days Per Week** | Work days | 5 |
| **Work Days** | Specific days | "0,1,2,3,4" (Mon-Fri) |

**How This Is Used:**
- Lead time calculations use business days
- Scheduling respects working hours
- Shipping estimates account for non-business days

### 9.3 Quote and Invoice Settings

**Navigation:** Settings → Company → **Documents**

**Quote Settings:**

| Field | Description | Example |
|-------|-------------|---------|
| **Default Validity Days** | Days quote stays valid | 30 |
| **Quote Terms** | Terms & conditions text | "Payment due within 30 days..." |
| **Quote Footer** | Footer on quote documents | "Thank you for your business!" |

**Invoice Settings:**

| Field | Description | Example |
|-------|-------------|---------|
| **Invoice Prefix** | Prefix for invoice numbers | "INV" |
| **Invoice Terms** | Payment terms text | "Net 30" |

---

## 10. Admin Dashboard

### 10.1 Dashboard Overview

**Navigation:** Home or Dashboard icon

The admin dashboard provides a real-time operational overview.

**Key Metric Cards:**

| Metric | What It Shows |
|--------|--------------|
| **Pending Quotes** | Quotes awaiting response |
| **Orders in Production** | Active production orders |
| **Ready to Ship** | Orders waiting for shipping |
| **Overdue Orders** | Orders past due date |
| **Low Stock Items** | Items below reorder point |
| **MRP Shortages** | Materials with shortages |
| **Revenue (30-day)** | Sales in last 30 days |
| **Revenue (YTD)** | Year-to-date sales |

### 10.2 Trend Charts

**Available Trends:**

| Chart | Description | Periods |
|-------|-------------|---------|
| **Sales Trend** | Daily sales and payments | WTD, MTD, QTD, YTD, ALL |
| **Shipping Trend** | Daily shipped orders | Same |
| **Production Trend** | Daily completed production | Same |
| **Purchasing Trend** | Daily PO receipts and spend | Same |

**How to Use:**
1. Select trend chart
2. Choose period (Week-to-Date, Month-to-Date, etc.)
3. View daily breakdown with totals

### 10.3 Profit Summary

**Navigation:** Dashboard → **Profit Summary**

| Metric | Formula |
|--------|---------|
| **Revenue** | Sum of completed sales |
| **COGS** | Cost of Goods Sold (materials + manufacturing) |
| **Gross Profit** | Revenue - COGS |
| **Gross Margin** | (Gross Profit / Revenue) x 100% |

### 10.4 Quick Actions

The dashboard provides quick-action buttons for common tasks:
- Create Sales Order
- Create Production Order
- Run MRP
- View Low Stock Items
- View Pending BOMs

---

## 11. System Administration

### 11.1 System Version

**Navigation:** Settings → **System**

View your current FilaOps version information:
- Version number (from git tag)
- Environment (development/production)
- Database connection status
- Tier (Community)

### 11.2 System Updates (Docker)

**Navigation:** Settings → System → **Update**

For Docker-based deployments, FilaOps supports one-click updates:

**Update Process:**
1. Navigate to Settings → System → Update
2. Click **Check for Updates**
3. If update available, review changes
4. Click **Start Update**

**What Happens:**
1. Pulls latest code from git repository
2. Rebuilds Docker containers
3. Runs database migrations (Alembic)
4. Restarts services
5. Reports success or failure

**Update Status Values:**
- **Idle** - No update in progress
- **Checking** - Looking for updates
- **Updating** - Update in progress
- **Success** - Update completed
- **Error** - Update failed (check logs)

**To Update to a Specific Version:**
- Enter a specific version tag (e.g., "v3.1.0")
- Click **Start Update**

### 11.3 Environment Configuration

Key environment variables in `backend/.env`:

**Essential Settings:**

| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_URL` | Database connection | `postgresql+psycopg://...` |
| `SECRET_KEY` | JWT signing key | Random 64-char hex string |
| `ENVIRONMENT` | Dev or production | `development` |
| `ALLOWED_ORIGINS` | CORS origins | `http://localhost:5173` |

**MRP Settings:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `INCLUDE_SALES_ORDERS_IN_MRP` | false | Include SOs as MRP demand |
| `AUTO_MRP_ON_ORDER_CREATE` | false | Auto-run MRP on new orders |
| `MRP_ENABLE_SUB_ASSEMBLY_CASCADING` | false | Lead time cascading |

**Manufacturing Settings:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `MACHINE_HOURLY_RATE` | 1.50 | Default machine rate ($/hr) |
| `PRINTING_HOURS_PER_DAY` | 8 | Daily printing capacity |
| `PROCESSING_BUFFER_DAYS` | 2 | Buffer days for production |

**See the [Getting Started](getting-started.md) guide for complete `.env` setup.**

---

## 12. Data Import and Export

### 12.1 Available Imports

FilaOps supports bulk data import for:

| Data Type | Format | Navigation |
|-----------|--------|------------|
| **Materials** | CSV | Settings → Materials → Import |
| **Printers** | CSV | Settings → Printers → Import |
| **Customers** | CSV | Sales → Customers → Import |
| **Products** | CSV | Items → Import |

**Import Process:**
1. Download the CSV template (ensures correct columns)
2. Fill in data using a spreadsheet editor
3. Upload the CSV file
4. Choose import options:
   - **Update Existing** - Overwrite matching records
   - **Skip Existing** - Only add new records
5. Preview results
6. Confirm import

### 12.2 Export

**Navigation:** Admin → **Export**

Export data from FilaOps for:
- Backup purposes
- Reporting in external tools
- Migration to other systems

### 12.3 Seed Example Data

**Navigation:** Settings → **Seed Data** (or via API)

For new installations, seed example data to explore FilaOps:

**What Gets Created:**
- Example items (finished goods, packaging, hardware)
- Material types (PLA, PETG, ABS, TPU, etc.)
- Basic colors (Black, White, Gray, Red, Blue, etc.)
- Material-color combinations for common filaments

**To Seed:**
```
POST /api/v1/setup/seed-example-data
Authorization: Bearer YOUR_TOKEN
```

**See [Getting Started](getting-started.md) for details.**

---

## 13. Troubleshooting

### Issue 1: Can't Create New Users

**Symptoms:**
- "User limit reached" error
- Create button disabled

**Cause:** Community tier user limit reached

**Solution:**
1. Check Settings → Users for inactive accounts
2. Deactivate unused accounts
3. Or upgrade tier for more user slots

---

### Issue 2: Logo Upload Fails

**Symptoms:**
- "File too large" or "Invalid format" error

**Causes & Solutions:**

**File too large:**
```
Solution:
Maximum size is 2 MB.
1. Resize image to 400px wide
2. Compress PNG/JPEG
3. Try WebP format (smaller files)
```

**Wrong format:**
```
Solution:
Supported: PNG, JPEG, GIF, WebP
Not supported: SVG, BMP, TIFF
Convert to PNG if needed.
```

---

### Issue 3: Printer Not Connecting

**Symptoms:**
- Status stays "Offline"
- Test Connection fails

**Causes & Solutions:**

**Network issue:**
```
Solution:
1. Verify printer IP address is correct
2. Ensure FilaOps server can reach printer
3. Check firewall rules (ports 1883/MQTT, 80/HTTP)
4. Try pinging printer from server
```

**Wrong credentials:**
```
Solution:
1. Verify MQTT topic (Bambu Lab)
2. Check API key (OctoPrint)
3. Verify access code (Bambu Lab LAN mode)
```

**Printer not on network:**
```
Solution:
1. Check printer WiFi connection
2. Verify printer is on same subnet
3. Try printer discovery to find actual IP
```

---

### Issue 4: Tax Not Appearing on Quotes

**Symptoms:**
- Quotes show $0 tax
- Tax line missing

**Causes & Solutions:**

**Tax not enabled:**
```
Solution:
1. Settings → Company → Tax
2. Set Tax Enabled = Yes
3. Enter tax rate (e.g., 0.0825)
4. Save
```

**Tax rate set incorrectly:**
```
Solution:
Rate is DECIMAL, not percentage.
Wrong: 8.25 (this means 825% tax!)
Right: 0.0825 (this means 8.25% tax)
```

---

### Issue 5: AI Features Not Working

**Symptoms:**
- "AI not configured" error
- AI features grayed out

**Causes & Solutions:**

**No provider configured:**
```
Solution:
1. Settings → AI
2. Select provider (Anthropic or Ollama)
3. Enter credentials
4. Test connection
5. Save
```

**Anthropic API key invalid:**
```
Solution:
1. Verify key starts with "sk-ant-"
2. Check key hasn't expired
3. Verify billing is active on Anthropic account
4. Click "Test Connection"
```

**Ollama not running:**
```
Solution:
1. Check if Ollama is installed
2. Click "Start Ollama" button
3. Or manually: `ollama serve`
4. Verify URL is correct (default: http://localhost:11434)
```

---

### Issue 6: Company Settings Not Saving

**Symptoms:**
- Changes revert after refresh
- "Error saving settings" message

**Causes & Solutions:**

**Permission denied:**
```
Solution:
Only Admin users can change company settings.
1. Check your role (Settings → Users → Your account)
2. Contact admin if you need changes made
```

**Validation error:**
```
Solution:
Check for required fields:
1. Company name cannot be blank
2. Tax rate must be 0-1 range (decimal)
3. Fiscal year start must be 1-12
```

---

## 14. Quick Reference

### Navigation Map

```
Settings
├── Company
│   ├── Company Information (name, address, contact)
│   ├── Logo (upload/delete)
│   ├── Tax (enable, rate, registration)
│   ├── Accounting (fiscal year, method, currency)
│   ├── Schedule (timezone, business hours)
│   └── Documents (quote terms, invoice prefix)
├── Users
│   ├── User List (search, filter)
│   ├── Create User (admin/operator)
│   ├── Edit User (role, status, info)
│   └── Password Reset
├── Locations
│   ├── Location List (hierarchical)
│   └── Create/Edit Location
├── Materials
│   ├── Material Types (PLA, PETG, etc.)
│   ├── Colors (with hex codes)
│   ├── Material-Color Combos
│   └── Import (CSV)
├── Work Centers
│   ├── Work Center List
│   ├── Create/Edit (costing, capacity)
│   └── Resources (machines per center)
├── Printers
│   ├── Printer List (status, brand)
│   ├── Add Printer (manual or discover)
│   ├── Capabilities Configuration
│   └── Import (CSV)
├── AI
│   ├── Provider Selection
│   ├── Anthropic Config (API key, model)
│   └── Ollama Config (URL, model)
└── System
    ├── Version Info
    └── System Update (Docker)
```

### User Roles

| Role | Code | Settings | Users | Operations | Accounting |
|------|------|----------|-------|------------|------------|
| **Admin** | `admin` | Full | Full | Full | Full |
| **Operator** | `operator` | View | None | Full | None |
| **Customer** | `customer` | None | Own profile | None | None |

### Account Status

| Status | Login | Data | Reversible |
|--------|-------|------|------------|
| **Active** | Yes | Accessible | N/A |
| **Inactive** | No | Preserved | Yes (Reactivate) |
| **Suspended** | No | Preserved | Yes (Admin action) |

### API Endpoints

**Company Settings:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/settings/company` | GET | Get company settings |
| `/api/v1/settings/company` | PATCH | Update company settings |
| `/api/v1/settings/company/logo` | POST | Upload logo |
| `/api/v1/settings/company/logo` | GET | Download logo |
| `/api/v1/settings/company/logo` | DELETE | Delete logo |

**User Management:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/admin/users` | GET | List users |
| `/api/v1/admin/users` | POST | Create user |
| `/api/v1/admin/users/{id}` | GET | Get user |
| `/api/v1/admin/users/{id}` | PATCH | Update user |
| `/api/v1/admin/users/{id}` | DELETE | Deactivate user |
| `/api/v1/admin/users/{id}/reactivate` | POST | Reactivate user |
| `/api/v1/admin/users/{id}/reset-password` | POST | Reset password |
| `/api/v1/admin/users/stats/summary` | GET | User stats |

**Locations:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/locations` | GET | List locations |
| `/api/v1/locations` | POST | Create location |
| `/api/v1/locations/{id}` | GET | Get location |
| `/api/v1/locations/{id}` | PUT | Update location |
| `/api/v1/locations/{id}` | DELETE | Deactivate location |

**AI Settings:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/settings/ai` | GET | Get AI config |
| `/api/v1/settings/ai` | PATCH | Update AI config |
| `/api/v1/settings/ai/test` | POST | Test AI connection |
| `/api/v1/settings/ai/start-ollama` | POST | Start Ollama service |

**Work Centers:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/work-centers` | GET | List work centers |
| `/api/v1/work-centers` | POST | Create work center |
| `/api/v1/work-centers/{id}` | GET | Get work center |
| `/api/v1/work-centers/{id}` | PUT | Update work center |
| `/api/v1/work-centers/{id}/resources` | GET | List resources |
| `/api/v1/work-centers/{id}/resources` | POST | Add resource |

**Printers:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/printers` | GET | List printers |
| `/api/v1/printers` | POST | Create printer |
| `/api/v1/printers/{id}` | GET | Get printer |
| `/api/v1/printers/{id}` | PUT | Update printer |
| `/api/v1/printers/{id}/test-connection` | POST | Test connection |
| `/api/v1/printers/discover` | POST | Network discovery |
| `/api/v1/printers/brands/info` | GET | Supported brands |

### Key Environment Variables

```ini
# Core
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/filaops
SECRET_KEY=your-64-char-hex-secret
ENVIRONMENT=development

# CORS
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# MRP
INCLUDE_SALES_ORDERS_IN_MRP=false
AUTO_MRP_ON_ORDER_CREATE=false
MRP_ENABLE_SUB_ASSEMBLY_CASCADING=false

# Manufacturing
MACHINE_HOURLY_RATE=1.50
PRINTING_HOURS_PER_DAY=8

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

## Related Guides

- **[Getting Started](getting-started.md)** - Initial setup, environment configuration, first-time wizard
- **[Inventory Management](inventory-management.md)** - Using locations for stock management
- **[Manufacturing](manufacturing.md)** - Work centers and routing operations
- **[MRP](mrp.md)** - MRP configuration settings
- **[Sales & Quotes](sales-and-quotes.md)** - Quote terms and tax on quotes
- **[Purchasing](purchasing.md)** - Vendor management and purchase orders

---

**Need Help?**
- Consult the [API Reference](../API-REFERENCE.md) for integration details
- Report issues on [GitHub](https://github.com/Blb3D/filaops/issues)
- See [Getting Started](getting-started.md) for initial setup

---

*Last Updated: February 2026 | FilaOps v3.0.0*
