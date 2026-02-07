# Printers & Fleet Monitoring Guide

This guide covers FilaOps' printer management system, including multi-brand printer registration, network discovery, MQTT monitoring, maintenance tracking, and fleet dashboard capabilities.

## Overview

FilaOps provides a **brand-agnostic printer management system** designed for 3D print farms of any size. Whether you run 2 printers or 200, FilaOps can register, monitor, and schedule work across your fleet.

**Key Features:**
- Multi-brand support (Bambu Lab, Klipper, OctoPrint, Prusa, Creality, Generic)
- Automatic network discovery (SSDP, mDNS)
- Real-time MQTT monitoring for Bambu Lab printers
- Connection testing and diagnostics
- Preventive maintenance tracking and scheduling
- Work center integration for production scheduling
- Print job tracking with time and material variance
- Bulk CSV import for large fleets
- Camera and AMS (Auto Material System) support detection

**Fleet Management Flow:**
```
Register Printers → Configure Connections → Monitor Status →
Assign to Work Centers → Schedule Production → Track Maintenance
```

**Who Uses This Module:**
- **Administrators** - Full access to printer management and configuration
- **Operators** - Full access to monitoring and operational features

---

## Table of Contents

1. [Supported Printer Brands](#1-supported-printer-brands)
2. [Adding Printers](#2-adding-printers)
3. [Network Discovery](#3-network-discovery)
4. [Connection Testing](#4-connection-testing)
5. [Printer Status and Monitoring](#5-printer-status-and-monitoring)
6. [MQTT Monitoring (Bambu Lab)](#6-mqtt-monitoring-bambu-lab)
7. [Fleet Dashboard](#7-fleet-dashboard)
8. [Print Job Tracking](#8-print-job-tracking)
9. [Maintenance Tracking](#9-maintenance-tracking)
10. [Work Center Integration](#10-work-center-integration)
11. [Bulk Import](#11-bulk-import)
12. [Tier Limits](#12-tier-limits)
13. [Common Workflows](#13-common-workflows)
14. [Best Practices](#14-best-practices)
15. [Troubleshooting](#15-troubleshooting)
16. [Quick Reference](#16-quick-reference)

---

## 1. Supported Printer Brands

### 1.1 Brand Overview

FilaOps uses a **pluggable adapter architecture** that supports multiple 3D printer brands:

| Brand | Connection | Discovery | Monitoring | Camera |
|-------|-----------|-----------|------------|--------|
| **Bambu Lab** | MQTT / LAN | SSDP (auto) | Real-time telemetry | Yes |
| **Klipper** | Moonraker HTTP | mDNS (auto) | Status polling | Webcam |
| **OctoPrint** | REST API | HTTP probe | Status polling | Webcam |
| **Prusa** | PrusaLink | Manual | Basic status | Varies |
| **Creality** | Network | Manual | Basic status | Varies |
| **Generic** | Manual | N/A | Manual updates | N/A |

### 1.2 Bambu Lab Printers

**Supported Models:**
- X1 Carbon (X1C) - Enclosed, multi-material AMS
- P1S - Enclosed, AMS optional
- P1P - Open frame
- A1 - Open frame, AMS Lite
- A1 Mini - Compact, AMS Lite

**Connection Requirements:**
- Same local network as FilaOps server
- LAN mode enabled on printer
- Access code (from printer settings)
- Serial number (for MQTT topic)

**Features:**
- Real-time status via MQTT
- Print progress percentage
- Temperature monitoring (nozzle, bed, chamber)
- AMS filament slot tracking
- Camera feed (if supported)

### 1.3 Klipper Printers

**Connection Requirements:**
- Moonraker API running (default port 7125)
- API key (if authentication enabled)
- Network accessible from FilaOps server

**Features:**
- Print status and progress
- Temperature monitoring
- Webcam support (via Moonraker)

### 1.4 OctoPrint Printers

**Connection Requirements:**
- OctoPrint server running (default port 5000 or 80)
- API key from OctoPrint settings
- Network accessible from FilaOps server

**Features:**
- Print status and progress
- Temperature monitoring
- Webcam support

### 1.5 Generic Printers

For printers without network connectivity or unsupported brands:
- Manual status updates only
- No automatic monitoring
- Used for tracking and scheduling purposes

---

## 2. Adding Printers

### 2.1 Manual Registration

**Navigation:** Settings → **Printers** → **+ New Printer**

**Step 1: Basic Information**

```
Code: PRT-001 (auto-generated or custom)
Name: Leonardo (descriptive name)
Brand: bambulab
Model: X1C (from brand's model list)
Serial Number: 01P00A123456789 (for tracking)
```

**Step 2: Network Configuration**

```
IP Address: 192.168.1.100
MQTT Topic: (auto-derived from serial for Bambu Lab)

Connection Config (brand-specific):
  Bambu Lab:
    Access Code: 12345678 (from printer LCD)
    Serial: 01P00A123456789

  Klipper:
    Port: 7125
    API Key: (if required)

  OctoPrint:
    Port: 80
    API Key: abc123def456...
```

**Step 3: Capabilities**

```
Bed Size: 256 x 256 x 256 mm
Heated Bed: Yes
Enclosure: Yes (required for ABS/ASA/PC)
AMS Slots: 4 (Bambu Lab AMS)
Camera: Yes
Max Nozzle Temp: 300 C
Max Bed Temp: 120 C
```

**Step 4: Organization**

```
Location: "Rack A, Shelf 2" (physical location description)
Work Center: FDM-POOL (production area assignment)
Notes: "Dedicated to PETG production"
```

**Step 5: Save**

Click **Create Printer** → Printer registered and ready for monitoring

### 2.2 Auto-Generated Codes

If you leave the code blank, FilaOps generates one automatically:

| Brand | Prefix | Example |
|-------|--------|---------|
| Bambu Lab | BAM | BAM-001 |
| Klipper | KLP | KLP-001 |
| OctoPrint | OCT | OCT-001 |
| Generic | PRT | PRT-001 |

**To generate a code manually:**

**Navigation:** Settings → Printers → **Generate Code**
- Select prefix (e.g., "PRT")
- System returns next available code (PRT-003)

---

## 3. Network Discovery

### 3.1 Automatic Discovery

FilaOps can automatically find printers on your local network.

**Navigation:** Settings → Printers → **Discover**

**Step 1: Configure Discovery**

```
Brands to Scan:
  ☑ Bambu Lab (SSDP on port 1990)
  ☑ Klipper (mDNS / Moonraker)
  ☐ OctoPrint (HTTP probe)

Timeout: 5 seconds (1-30 seconds)
```

**Step 2: Run Discovery**

Click **Start Discovery** → System scans the network

**Step 3: Review Results**

```
Discovery Results (scanned in 4.2 seconds)
═══════════════════════════════════════════════════════════
Found  Brand      Model  IP Address      Serial          Status
═══════════════════════════════════════════════════════════
✅ New  Bambu Lab  X1C   192.168.1.100   01P00A123456   Not registered
✅ New  Bambu Lab  P1S   192.168.1.101   01P00B789012   Not registered
⚠️ Dup  Bambu Lab  A1    192.168.1.102   01P00C345678   Already registered
✅ New  Klipper    -     192.168.1.110   -              Not registered
═══════════════════════════════════════════════════════════
Found: 4 printers (3 new, 1 duplicate)
```

**Step 4: Add Discovered Printers**

- Click **Add** next to each new printer
- Pre-fills brand, model, IP address, serial number
- Review and customize name, code, location
- Click **Save**

### 3.2 IP Probe

For Docker deployments or when SSDP/mDNS doesn't work, probe a specific IP:

**Navigation:** Settings → Printers → **Probe IP**

```
IP Address: 192.168.1.100

Result:
  Open Ports:
    ✅ 8883 (MQTT - Bambu Lab)
    ✅ 80 (HTTP)
    ❌ 7125 (Moonraker - not found)
    ❌ 5000 (OctoPrint - not found)

  Detected Brand: Bambu Lab
  Suggested Code: BAM-003
```

**Use Cases:**
- Printer not found by automatic discovery
- Running FilaOps in Docker (SSDP doesn't cross container boundaries)
- Confirming a specific printer's network presence

### 3.3 Discovery Protocol Details

| Brand | Protocol | Port | Method |
|-------|----------|------|--------|
| Bambu Lab | SSDP | 1990 | UDP multicast broadcast |
| Klipper | mDNS | 7125 | DNS service discovery |
| OctoPrint | HTTP | 5000/80 | HTTP API probe |
| Prusa | Manual | - | Not auto-discoverable |
| Creality | Manual | - | Not auto-discoverable |

---

## 4. Connection Testing

### 4.1 Testing a Printer Connection

Before relying on monitoring, verify the connection works.

**Navigation:** Settings → Printers → Select printer → **Test Connection**

**Or before adding:** Settings → Printers → **Test Connection** (standalone)

**Input:**
```
IP Address: 192.168.1.100
Brand: bambulab
Connection Config:
  Access Code: 12345678
  Serial: 01P00A123456789
```

**Output (Success):**
```
✅ Connection Successful
  Response Time: 42ms
  Printer Status: Idle
  Model: X1C
  Firmware: 01.07.00.00
```

**Output (Failure):**
```
❌ Connection Failed
  Error: Connection timed out after 5000ms
  Suggestion: Check IP address and network connectivity
```

### 4.2 Common Connection Issues

| Error | Cause | Solution |
|-------|-------|---------|
| Connection timeout | Wrong IP or printer offline | Verify IP, check printer power/WiFi |
| Authentication failed | Wrong access code or API key | Re-enter credentials from printer |
| Port not open | Firewall blocking | Check firewall rules for required ports |
| MQTT connection refused | LAN mode not enabled | Enable LAN mode on Bambu Lab printer |

---

## 5. Printer Status and Monitoring

### 5.1 Printer Status Values

| Status | Meaning | Indicator | Auto-Detected? |
|--------|---------|-----------|---------------|
| **offline** | Not seen in 5+ minutes | Gray | Yes |
| **idle** | Connected, no job running | Green | Yes |
| **printing** | Active print in progress | Blue | Yes |
| **paused** | Print paused | Yellow | Yes |
| **error** | Error state | Red | Yes |
| **maintenance** | Under maintenance | Orange | Manual only |

### 5.2 Online Detection

A printer is considered **online** if it was last seen within **5 minutes**. The `last_seen` timestamp updates whenever:

- MQTT telemetry is received (Bambu Lab)
- API poll returns successfully (Klipper, OctoPrint)
- Manual status update is performed

### 5.3 Updating Status Manually

For printers without automatic monitoring (Generic brand or network issues):

**Navigation:** Settings → Printers → Select printer → **Update Status**

```
New Status: maintenance
Notes: "Nozzle replacement scheduled"
```

**Or via API:**
```
PATCH /api/v1/printers/{id}/status
Body: { "status": "maintenance" }
```

### 5.4 Printer List View

**Navigation:** Settings → **Printers** (or Printers module in sidebar)

**Columns:**
- Code (PRT-001, BAM-001, etc.)
- Name
- Brand and Model
- IP Address
- Status (with color indicator)
- Online (last seen timestamp)
- Work Center
- Location

**Filters:**
- Search (name, code, model, location)
- Brand
- Status
- Active only

---

## 6. MQTT Monitoring (Bambu Lab)

### 6.1 How MQTT Monitoring Works

For Bambu Lab printers, FilaOps connects via MQTT (Message Queuing Telemetry Transport) for real-time monitoring:

```
Bambu Lab Printer
    │
    ├── MQTT Broker (port 8883 TLS)
    │
    ▼
FilaOps MQTT Service
    │
    ├── Telemetry Events (temperature, progress, status)
    ├── Print Job Status (started, progress, completed, failed)
    └── AMS Filament Info (slot, material, color)
```

### 6.2 Enabling MQTT Monitoring

**Prerequisites:**
1. Bambu Lab printer on same LAN as FilaOps server
2. LAN mode enabled on printer
3. Access code obtained from printer settings
4. Printer registered in FilaOps with correct serial number

**The MQTT monitor service starts automatically** when the FilaOps backend starts. It:
1. Loads all active Bambu Lab printers from the database
2. Establishes MQTT connections to each printer
3. Receives telemetry events in real-time
4. Queues events for processing (up to 1,000 events)
5. Periodically flushes status updates to the database

### 6.3 Telemetry Data

**Available data from MQTT telemetry:**

| Data Point | Description | Update Frequency |
|-----------|-------------|-----------------|
| Print Status | Idle, printing, paused, error | On change |
| Print Progress | 0-100% completion | Every few seconds |
| Nozzle Temperature | Current/target nozzle temp | Every few seconds |
| Bed Temperature | Current/target bed temp | Every few seconds |
| Chamber Temperature | Enclosed chamber temp | Every few seconds |
| Print Speed | Current speed profile | On change |
| Layer Progress | Current layer / total layers | On layer change |
| Remaining Time | Estimated minutes remaining | Periodically |
| AMS Status | Filament type/color per slot | On change |

### 6.4 Event Processing

The MQTT service processes events through an **event queue**:

1. **Receive** - MQTT message arrives from printer
2. **Parse** - Extract telemetry data
3. **Queue** - Add to event queue (max 1,000 events)
4. **Process** - Update in-memory printer state
5. **Flush** - Periodically write status to database

**This architecture ensures:**
- No missed events during high-frequency updates
- Database isn't overwhelmed with writes
- Real-time display in the UI
- Historical data recorded at reasonable intervals

---

## 7. Fleet Dashboard

### 7.1 Fleet Overview

**Navigation:** Printers (in sidebar)

The fleet dashboard shows all registered printers at a glance:

```
Fleet Status Summary
═══════════════════════════════════════
Online:      6 / 8 printers
Printing:    4
Idle:        2
Offline:     1
Maintenance: 1
═══════════════════════════════════════
```

### 7.2 Printer Cards

Each printer displays as a card with:

```
┌─────────────────────────────────────┐
│ 🟢 Leonardo (X1C)           BAM-001│
│ Status: Printing (67%)              │
│ Nozzle: 220°C / 220°C              │
│ Bed: 60°C / 60°C                   │
│ Layer: 145 / 217                    │
│ Time Remaining: 1h 23m             │
│ Job: Phone Stand v3                 │
│ Work Center: FDM-POOL              │
│ Location: Rack A, Shelf 1          │
└─────────────────────────────────────┘
```

### 7.3 Active Work View

**Navigation:** Printers → **Active Work**

Shows current and queued production work per printer:

```
Active Work Assignments
═══════════════════════════════════════════════════════════
Printer         Current Job              Queue
═══════════════════════════════════════════════════════════
Leonardo (X1C)  PO-2026-042 (OP-10)     2 queued
                Phone Stand × 10
                Status: printing (67%)

Donatello (X1C) PO-2026-043 (OP-10)     1 queued
                Bracket × 25
                Status: printing (34%)

Michelangelo    (idle)                   0 queued
Raphael         (maintenance)            0 queued
═══════════════════════════════════════════════════════════
```

**Columns:**
- Printer name and model
- Current production order and operation
- Product and quantity
- Operation status (running/queued)
- Queue depth (number of waiting jobs)

---

## 8. Print Job Tracking

### 8.1 What is a Print Job?

A **Print Job** represents a single print operation on a specific printer. It links a production order operation to a physical printer.

### 8.2 Print Job Statuses

| Status | Meaning | Triggered By |
|--------|---------|-------------|
| **queued** | Waiting to start | Job assigned to printer |
| **assigned** | Assigned, awaiting start | Operator confirms |
| **printing** | Currently printing | MQTT status or manual start |
| **completed** | Print finished successfully | MQTT status or manual complete |
| **failed** | Print failed | MQTT error or manual report |

### 8.3 Job Details

Each print job tracks:

```
Print Job: JOB-2026-0042
═══════════════════════════════════════
Production Order: PO-2026-0042
Printer: Leonardo (BAM-001)
Priority: Normal

File: phone_stand_v3.gcode

Timing:
  Estimated: 150 minutes
  Actual: 156 minutes
  Variance: +4% (6 min over)

Material:
  Estimated: 450 grams
  Actual: 462 grams
  Variance: +2.7% (12 g over)

Timestamps:
  Queued:    2026-02-07 08:00
  Started:   2026-02-07 08:15
  Finished:  2026-02-07 10:51

Status: completed
Notes: "First layer looked good, no issues"
═══════════════════════════════════════
```

### 8.4 Variance Tracking

FilaOps calculates the percentage difference between estimated and actual values:

```
Time Variance = ((Actual - Estimated) / Estimated) × 100%
Material Variance = ((Actual - Estimated) / Estimated) × 100%
```

**Target variances:**
- Time: < 10% (reasonable)
- Material: < 5% (good slicer estimates)

**High variances indicate:**
- Inaccurate slicer estimates (update profiles)
- Print quality issues (supports, retraction, speed)
- Material waste (failed starts, purge)

---

## 9. Maintenance Tracking

### 9.1 Maintenance Types

| Type | Description | Frequency |
|------|-------------|-----------|
| **routine** | Scheduled preventive maintenance | Weekly/monthly |
| **repair** | Emergency fix for breakdowns | As needed |
| **calibration** | Bed leveling, extrusion calibration | Monthly |
| **cleaning** | Nozzle, bed, enclosure cleaning | Weekly |

### 9.2 Recording Maintenance

**Navigation:** Printers → Select printer → **Maintenance** → **+ Log Maintenance**

```
Maintenance Type: routine
Description: "Weekly nozzle cleaning and bed inspection"
Performed By: "John Smith"
Performed At: 2026-02-07 09:00

Cost: $5.00 (nozzle replacement parts)
Downtime: 30 minutes

Parts Used: "0.4mm hardened steel nozzle"

Next Due: 2026-02-14 (in 7 days)

Notes: "Noticed slight wear on bed surface,
        monitor for next 2 weeks"
```

### 9.3 Maintenance History

**Navigation:** Printers → Select printer → **Maintenance History**

```
Maintenance Log: Leonardo (BAM-001)
═══════════════════════════════════════════════════════════
Date       Type         Description           Cost  Downtime
═══════════════════════════════════════════════════════════
2026-02-07 routine      Weekly nozzle clean    $5     30 min
2026-01-31 calibration  Bed level + flow cal   $0     45 min
2026-01-25 repair       PTFE tube replacement  $8     60 min
2026-01-24 routine      Weekly nozzle clean    $0     30 min
═══════════════════════════════════════════════════════════
Total Cost: $13.00
Total Downtime: 2 hrs 45 min
```

### 9.4 Scheduling Next Maintenance

When recording maintenance, set the **Next Due** date. The system will show upcoming maintenance in the fleet dashboard.

```
Upcoming Maintenance (Next 7 Days)
═══════════════════════════════════════
Printer         Type        Due Date
═══════════════════════════════════════
Leonardo        routine     Feb 14
Donatello       calibration Feb 12
Michelangelo    routine     Feb 14
═══════════════════════════════════════
```

---

## 10. Work Center Integration

### 10.1 Assigning Printers to Work Centers

Each printer can belong to a **Work Center** for production scheduling:

```
Work Center: FDM-POOL
  ├── Leonardo (X1C) - BAM-001
  ├── Donatello (X1C) - BAM-002
  ├── Michelangelo (P1S) - BAM-003
  └── Raphael (P1S) - BAM-004
```

**To assign:**
1. Navigate to Printers → Select printer → Edit
2. Select Work Center: FDM-POOL
3. Save

**Or from Work Centers:**
1. Settings → Work Centers → FDM-POOL
2. Resources tab → + Add Resource
3. Select printer

### 10.2 How Scheduling Uses Printers

When a production order operation is assigned to a work center:

1. **Operation** → Assigned to **Work Center** (FDM-POOL)
2. **Work Center** → Contains **Printers** (Leonardo, Donatello, etc.)
3. **Scheduler** → Assigns operation to specific **Printer** based on:
   - Availability (idle, not in maintenance)
   - Capability (enclosure for ABS, bed size for large parts)
   - Queue depth (balance load)
   - Priority (rush orders first)

### 10.3 Material Compatibility

Printers with **enclosures** can print all materials. Open-frame printers are limited:

| Printer Type | PLA | PETG | TPU | ABS | ASA | PC |
|-------------|-----|------|-----|-----|-----|-----|
| Open frame (A1, A1 Mini) | Yes | Yes | Yes | No | No | No |
| Enclosed (P1S, X1C) | Yes | Yes | Yes | Yes | Yes | Yes |

**Scheduling enforces these constraints** - ABS orders won't be assigned to open-frame printers.

---

## 11. Bulk Import

### 11.1 CSV Import

For large print farms, import printers from a CSV file.

**Navigation:** Settings → Printers → **Import**

**Step 1: Download Template**

Click **Download Template** to get the CSV format:

```csv
code,name,model,brand,serial_number,ip_address,location,notes
BAM-001,Leonardo,X1C,bambulab,01P00A123456,192.168.1.100,Rack A Shelf 1,Primary printer
BAM-002,Donatello,X1C,bambulab,01P00A789012,192.168.1.101,Rack A Shelf 2,
BAM-003,Michelangelo,P1S,bambulab,01P00B345678,192.168.1.102,Rack B Shelf 1,
KLP-001,Voron 2.4,voron,klipper,,192.168.1.110,Rack C,Custom build
```

**Required Columns:**
- `code` - Unique printer code
- `name` - Human-readable name
- `model` - Printer model

**Optional Columns:**
- `brand` - Printer brand (defaults to "generic")
- `serial_number` - Serial number
- `ip_address` - Network address
- `location` - Physical location
- `notes` - Additional information

**Step 2: Upload and Import**

```
Upload CSV: [Select File]
Skip Duplicates: ☑ (skip rows where code already exists)
```

**Step 3: Review Results**

```
Import Results
═══════════════════════════════════
Total Rows: 10
Imported: 8
Skipped (duplicates): 1
Errors: 1
  Row 7: Missing required field 'name'
═══════════════════════════════════
```

### 11.2 Import Tips

- **code** must be unique across all printers
- **brand** must be one of: bambulab, klipper, octoprint, prusa, creality, generic
- All imported printers start with status `offline`
- Connection config (access codes, API keys) must be added manually after import
- Use **Skip Duplicates** to safely re-run imports

---

## 12. Tier Limits

### 12.1 Community Tier

The **Community (open-source) tier** has a limit on active printers:

| Tier | Active Printer Limit |
|------|---------------------|
| Community | 4 printers |

**Active** means `active = true`. You can register more printers but only 4 can be active at once.

### 12.2 Managing Within Limits

If you hit the limit:
1. Deactivate printers not currently in use
2. Swap active/inactive as needed
3. Inactive printers retain all history and configuration

**To deactivate:**
1. Printers → Select printer → Edit
2. Set Active: No
3. Save (printer hidden from scheduling and monitoring)

**To reactivate:**
1. Printers → Filter: Show Inactive
2. Select printer → Edit
3. Set Active: Yes (will fail if at tier limit)

---

## 13. Common Workflows

### Workflow 1: Setting Up a New Printer

```
1. Unbox and connect printer to WiFi
2. Note the IP address and serial number
3. Enable LAN mode (Bambu Lab):
   - Printer LCD → Settings → Network → LAN Mode
   - Note the access code
4. Register in FilaOps:
   - Printers → + New Printer
   - Enter: name, brand, model, IP, serial, access code
   - Assign to work center
5. Test connection:
   - Click "Test Connection"
   - Verify: ✅ Connected
6. Verify MQTT monitoring:
   - Wait 30 seconds
   - Check status updates to "idle"
   - ✅ Printer online and monitored
```

**Time estimate:** 10 minutes

### Workflow 2: Fleet Discovery (New Setup)

```
1. Ensure all printers are on the network
2. Navigate to Printers → Discover
3. Select brands to scan
4. Click "Start Discovery"
5. Review found printers:
   - 6 printers found
   - 0 duplicates
6. Click "Add" for each printer
7. Customize names and codes
8. Assign to work centers
9. Test all connections
10. Verify monitoring is active
```

**Time estimate:** 20 minutes for 6 printers

### Workflow 3: Weekly Maintenance Routine

```
1. Check fleet dashboard for maintenance due:
   - Leonardo: routine cleaning due today
   - Donatello: calibration due tomorrow

2. Mark Leonardo as "maintenance":
   - Update status to maintenance
   - Production scheduler stops assigning jobs

3. Perform maintenance:
   - Clean nozzle
   - Inspect bed surface
   - Check belt tension
   - Run calibration print

4. Log maintenance:
   - Printers → Leonardo → Maintenance → + Log
   - Type: routine
   - Description: "Weekly clean + belt check"
   - Downtime: 30 min
   - Next due: +7 days

5. Return to service:
   - Update status to idle
   - Scheduler resumes assigning jobs

6. Repeat for Donatello's calibration
```

**Time estimate:** 30-45 minutes per printer

### Workflow 4: Handling a Print Failure

```
1. MQTT reports: Leonardo status = error
2. Fleet dashboard shows red indicator
3. Investigate:
   - Check printer display for error code
   - View camera feed (if available)
   - Found: Spaghetti failure (poor adhesion)
4. Clear the failure:
   - Remove failed print from bed
   - Clean bed surface
   - Reset printer
5. Update in FilaOps:
   - Print job status → failed
   - Notes: "First layer adhesion failure"
   - Scrap reason: adhesion
6. Restart production:
   - Printer status resets to idle
   - Re-queue the print job
   - Assign to same or different printer
7. Log if maintenance needed:
   - If recurring: Schedule bed replacement
```

### Workflow 5: Scaling the Fleet

```
1. Purchase new printers (e.g., 4 × P1S)
2. Network setup:
   - Connect all to WiFi
   - Assign static IPs (recommended)
   - Enable LAN mode
3. Bulk import:
   - Create CSV with all 4 printers
   - Import via Printers → Import
4. Configure connections:
   - Add access codes for each
   - Test connections
5. Assign to work center:
   - Add all to FDM-POOL
   - Update capacity: 8 printers → 12 printers
6. Update work center rates:
   - Adjust capacity hours/day
   - Machine depreciation rate may decrease (per-unit)
7. Verify monitoring:
   - All 4 showing "idle" on dashboard
   - MQTT connections established
8. Production ready:
   - MRP and scheduler now see additional capacity
```

---

## 14. Best Practices

### Fleet Management

- **Do:** Use consistent naming conventions (e.g., Printer-001, Printer-002)
- **Do:** Assign static IP addresses (printers changing IPs breaks monitoring)
- **Do:** Keep firmware updated across the fleet
- **Do:** Label physical printers with their FilaOps code
- **Do:** Assign all printers to work centers for scheduling

- **Don't:** Mix printer codes between logical groups
- **Don't:** Forget to update FilaOps when moving printers physically
- **Don't:** Ignore "offline" status for extended periods

### Monitoring

- **Do:** Check fleet dashboard daily for offline or error printers
- **Do:** Investigate failed prints promptly (prevent repeat failures)
- **Do:** Monitor print variance trends (consistent overestimates = update slicer)
- **Do:** Use camera feeds for remote monitoring when available

- **Don't:** Rely solely on automatic monitoring (check physically too)
- **Don't:** Ignore recurring error patterns

### Maintenance

- **Do:** Schedule routine maintenance weekly (nozzle, bed, belts)
- **Do:** Log all maintenance activities (builds history for planning)
- **Do:** Track costs and downtime (for OEE calculations)
- **Do:** Set the "Next Due" date for preventive scheduling

- **Don't:** Skip maintenance to save time (causes bigger failures)
- **Don't:** Forget to change status to "maintenance" before working on a printer
- **Don't:** Use a printer that needs repair for production

### Network

- **Do:** Use a dedicated VLAN or subnet for printers
- **Do:** Assign static IPs or DHCP reservations
- **Do:** Ensure FilaOps server can reach all printer IPs
- **Do:** Open required ports (8883 MQTT, 7125 Moonraker, 5000 OctoPrint)

- **Don't:** Put printers on guest WiFi
- **Don't:** Rely on DHCP without reservations (IP changes break connections)

---

## 15. Troubleshooting

### Printer Shows "Offline"

**Symptom:** Printer card shows gray "offline" status

**Causes & Solutions:**

**Network issue:**
```
1. Verify printer is powered on
2. Check printer's WiFi connection
3. Ping printer IP from FilaOps server
4. Check firewall rules
5. Verify printer and server are on same network/VLAN
```

**MQTT connection lost (Bambu Lab):**
```
1. Verify LAN mode is still enabled on printer
2. Check access code hasn't changed (firmware update can reset)
3. Re-enter access code in FilaOps printer config
4. Test connection to verify
```

**Monitoring service not running:**
```
1. Check FilaOps backend logs for MQTT errors
2. Restart backend service
3. MQTT service auto-reconnects on startup
```

### Discovery Finds No Printers

**Symptom:** Network discovery returns 0 results

**Causes & Solutions:**

**SSDP blocked (Bambu Lab):**
```
1. SSDP uses UDP multicast on port 1990
2. Some routers block multicast between subnets
3. Solution: Use IP probe instead of discovery
4. Or configure router to allow multicast
```

**Docker networking:**
```
1. Docker containers can't receive SSDP broadcasts
2. Use host networking mode for discovery
3. Or use IP probe with known addresses
```

**Printers not discoverable:**
```
1. Not all brands support auto-discovery
2. Prusa and Creality require manual registration
3. Use IP probe or manual entry instead
```

### Test Connection Fails

**Symptom:** "Connection Failed" when testing

**By Brand:**

**Bambu Lab:**
```
1. Check IP address is correct
2. Verify LAN mode enabled
3. Verify access code is correct
4. Port 8883 must be open (MQTT over TLS)
```

**Klipper:**
```
1. Check Moonraker is running
2. Verify port 7125 is accessible
3. Check API key if authentication is enabled
4. Try: curl http://{ip}:7125/server/info
```

**OctoPrint:**
```
1. Check OctoPrint is running
2. Verify API key in OctoPrint Settings → API
3. Try: curl -H "X-Api-Key: {key}" http://{ip}/api/version
```

### Print Job Stuck in "Queued"

**Symptom:** Job doesn't start printing

**Causes:**
```
1. Printer status not "idle" (check dashboard)
2. Printer not assigned to correct work center
3. Previous job not completed/cleared
4. Printer in maintenance mode
```

**Solution:**
```
1. Check printer status on dashboard
2. Clear any stuck jobs or error states
3. Verify work center assignment
4. Manually start the job if auto-dispatch fails
```

### High Material Variance

**Symptom:** Actual material usage consistently >10% over estimate

**Causes:**
```
1. Slicer estimates don't include purge/waste
2. Support material not accounted for
3. Failed starts (partial prints) consuming material
4. AMS filament changes adding purge waste
```

**Solution:**
```
1. Update slicer profile with more accurate flow rates
2. Add waste factor to BOM (5-10%)
3. Track failed starts separately
4. Account for AMS purge in material estimates
```

---

## 16. Quick Reference

### Printer Status Values

| Status | Color | Auto-Detected | Description |
|--------|-------|--------------|-------------|
| offline | Gray | Yes (timeout) | Not seen in 5+ min |
| idle | Green | Yes | Ready, no job |
| printing | Blue | Yes | Active print |
| paused | Yellow | Yes | Print paused |
| error | Red | Yes | Error state |
| maintenance | Orange | Manual | Under maintenance |

### Print Job Status Values

| Status | Meaning |
|--------|---------|
| queued | Waiting to start |
| assigned | Assigned to printer |
| printing | Currently printing |
| completed | Finished successfully |
| failed | Print failed |

### Maintenance Types

| Type | Frequency | Typical Duration |
|------|-----------|-----------------|
| routine | Weekly | 30 min |
| calibration | Monthly | 45 min |
| cleaning | Weekly | 15 min |
| repair | As needed | 30-120 min |

### Required Network Ports

| Port | Protocol | Brand | Purpose |
|------|----------|-------|---------|
| 8883 | TCP (TLS) | Bambu Lab | MQTT monitoring |
| 1990 | UDP | Bambu Lab | SSDP discovery |
| 7125 | TCP | Klipper | Moonraker API |
| 5000 | TCP | OctoPrint | REST API |
| 80/443 | TCP | Various | HTTP/HTTPS |

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/printers/` | GET | List printers |
| `/api/v1/printers/` | POST | Create printer |
| `/api/v1/printers/{id}` | GET | Get printer details |
| `/api/v1/printers/{id}` | PUT | Update printer |
| `/api/v1/printers/{id}` | DELETE | Delete printer |
| `/api/v1/printers/{id}/status` | PATCH | Update status |
| `/api/v1/printers/generate-code` | GET | Generate unique code |
| `/api/v1/printers/brands/info` | GET | Supported brands |
| `/api/v1/printers/discover` | POST | Network discovery |
| `/api/v1/printers/probe-ip` | POST | Probe single IP |
| `/api/v1/printers/test-connection` | POST | Test connectivity |
| `/api/v1/printers/import-csv` | POST | Bulk CSV import |
| `/api/v1/printers/active-work` | GET | Current/queued work |

---

## Related Guides

- **[Getting Started](getting-started.md)** - Initial setup and first-time configuration
- **[Manufacturing](manufacturing.md)** - Production orders, work centers, and scheduling
- **[Settings & Admin](settings-and-admin.md)** - Work center configuration and user management
- **[Inventory Management](inventory-management.md)** - Material tracking for print operations

---

**Need Help?**
- Consult the [API Reference](../API-REFERENCE.md) for integration details
- Report issues on [GitHub](https://github.com/Blb3D/filaops/issues)
- See [Getting Started](getting-started.md) for initial setup

---

*Last Updated: February 2026 | FilaOps v3.0.0*
