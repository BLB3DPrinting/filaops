# Getting Started with FilaOps

Welcome to FilaOps! This guide will walk you through installing and setting up FilaOps for the first time.

## What is FilaOps?

FilaOps is an open-source ERP system designed specifically for 3D print farm operations. It manages:

- **Inventory** - Track filament spools, hardware, packaging, and finished goods
- **Manufacturing** - Production orders, BOMs, routings, and MRP
- **Sales** - Quotes, sales orders, and fulfillment
- **Purchasing** - Vendor management and purchase orders
- **Accounting** - General ledger, journal entries, and basic financial reports
- **Printer Integration** - MQTT monitoring for Bambu Lab printer fleets

## Prerequisites

Before you begin, ensure you have the following installed:

| Software | Minimum Version | Download |
|----------|----------------|----------|
| **Python** | 3.11+ | [python.org](https://www.python.org/downloads/) |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) |
| **PostgreSQL** | 15+ | [postgresql.org](https://www.postgresql.org/download/) |
| **Git** | 2.0+ | [git-scm.com](https://git-scm.com/downloads/) |

**Note:** FilaOps requires PostgreSQL - SQLite is not supported due to the use of PostgreSQL-specific features (JSONB, arrays).

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Blb3D/filaops.git
cd filaops
```

### 2. Create PostgreSQL Database

Connect to PostgreSQL and create a database:

```bash
# Using psql
psql -U postgres

# In psql:
CREATE DATABASE filaops;
\q
```

Or using a GUI tool like pgAdmin, create a database named `filaops`.

### 3. Configure Environment Variables

Create a `.env` file in the `backend/` directory:

```bash
cd backend
cp .env.example .env  # If .env.example exists, otherwise create new .env
```

Edit `backend/.env` with your database connection details:

```ini
# Database Configuration
DATABASE_URL=postgresql+psycopg://postgres:your_password@localhost:5432/filaops

# Security
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=43200

# Environment
ENVIRONMENT=development

# Optional: CORS (if frontend runs on different port)
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

**⚠️ Important:** Change `your_password` to your PostgreSQL password, and generate a secure `SECRET_KEY` for production:

```bash
# Generate a secure secret key (Linux/Mac):
openssl rand -hex 32

# Or in Python:
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Set Up Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
.\venv\Scripts\Activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head
```

**Expected output:** You should see migration messages ending with "Running upgrade ... -> ..., [migration description]"

### 5. Set Up Frontend

Open a **new terminal window** (keep the backend terminal open):

```bash
cd frontend

# Install dependencies
npm install

# Optional: Check for vulnerabilities
npm audit
```

### 6. Start the Application

**Terminal 1 - Backend:**
```bash
cd backend
.\venv\Scripts\Activate  # or source venv/bin/activate on Linux/Mac
uvicorn app.main:app --reload
```

**You should see:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

**You should see:**
```
VITE v5.x.x  ready in xxx ms

➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
```

## First-Time Setup

### 1. Access the Setup Wizard

Open your browser and navigate to:

```
http://localhost:5173
```

If this is your first time running FilaOps (no users exist), you'll be automatically redirected to the **Setup Wizard**.

### 2. Create Admin Account

Fill in the setup form:

- **Email:** Your admin email (used for login)
- **Password:** Minimum 8 characters, must meet strength requirements
- **Full Name:** Your name (e.g., "John Smith")
- **Company Name:** Optional (e.g., "Acme 3D Printing")

Click **Create Admin Account**.

**✅ Success:** You'll be automatically logged in and taken to the dashboard.

### 3. Seed Example Data (Optional but Recommended)

To help you explore FilaOps, we recommend seeding example data. This creates:

- Example items in each category (finished goods, packaging, hardware)
- Material types (PLA, PETG, ABS, TPU, etc.)
- Basic colors (Black, White, Gray, Red, Blue, etc.)
- Material-color combinations for common filaments

**To seed data:**

1. After creating your admin account, you'll be logged in
2. Make a POST request to the seed endpoint (requires admin authentication):

**Using curl:**
```bash
# First, get your access token (it's automatically stored in the frontend)
# The seed endpoint is admin-only, so call it through the API:

# Using the frontend console:
# Open browser DevTools (F12) → Console → Run:
fetch('/api/v1/setup/seed-example-data', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + localStorage.getItem('access_token')
  }
}).then(r => r.json()).then(console.log)
```

**Or using a REST client like Postman:**
- Method: `POST`
- URL: `http://localhost:8000/api/v1/setup/seed-example-data`
- Headers: `Authorization: Bearer YOUR_ACCESS_TOKEN`

**✅ Success:** You'll see a response like:
```json
{
  "message": "Example data seeded successfully!",
  "items_created": 10,
  "items_skipped": 0,
  "materials_created": 18,
  "colors_created": 15,
  "links_created": 24,
  "material_products_created": 0
}
```

Now your system has example data to explore!

## Exploring FilaOps

### Dashboard Overview

After logging in, you'll see the **Admin Dashboard** with:

- **Sales Chart:** Visual of recent sales orders
- **Production Pipeline:** Current production orders by status
- **Recent Orders:** Latest sales orders
- **Quick Actions:** Buttons to create new records

### Navigation Menu

The left sidebar provides access to all modules:

| Icon | Module | What It Does |
|------|--------|--------------|
| 📊 | Dashboard | Overview and quick actions |
| 📦 | Items | Product catalog, BOMs, categories |
| 🏭 | Production | Production orders, operations, capacity |
| 📋 | MRP | Material Requirements Planning |
| 🛒 | Purchasing | Vendors, purchase orders, receiving |
| 💰 | Sales | Quotes, sales orders, customers |
| 🖨️ | Printers | MQTT fleet monitoring (Bambu Lab) |
| 📒 | Accounting | General ledger, journal entries, reports |
| ⚙️ | Settings | Company settings, users, locations |

## Creating Your First Sales Order

Let's walk through creating a complete sales order:

### 1. Create a Customer

**Navigation:** Sales → Customers → **+ New Customer**

Fill in:
- **Name:** "Acme Corporation"
- **Email:** customer@example.com
- **Phone:** (optional)
- **Address:** (optional)

Click **Save**. Customer code (e.g., `CUST-00001`) is auto-generated.

### 2. Create a Sales Order

**Navigation:** Sales → Sales Orders → **+ New Sales Order**

**Step 1: Customer Selection**
- Select customer: "Acme Corporation"
- Order date: (defaults to today)
- Due date: (optional)

**Step 2: Add Line Items**
- Click **+ Add Line**
- Select a product (e.g., "Example Standard Product")
- Quantity: 5
- Unit price: (auto-filled from product's selling price, or enter custom price)
- Click **Add**

**Step 3: Review and Submit**
- Review order total
- Add notes (optional)
- Click **Create Sales Order**

**✅ Success:** Your first sales order is created with status "Draft"!

### 3. View the Sales Order

The order appears in **Sales → Sales Orders** with:
- Auto-generated SO number (e.g., `SO-2026-00001`)
- Customer name
- Total amount
- Status: "Draft"

**Next steps:**
- Click **Confirm** to change status to "Confirmed"
- When ready to ship, mark as "Shipped"
- When payment received, mark as "Completed"

## What's Next?

Now that FilaOps is running, explore these guides:

| Guide | Learn About |
|-------|-------------|
| **Sales & Quotes** | Quote workflow, converting quotes to orders, pricing |
| **Inventory Management** | Stock adjustments, cycle counting, spool tracking |
| **Manufacturing** | Production orders, BOMs, routings, operations |
| **Purchasing** | Creating POs, receiving inventory, vendor management |
| **MRP** | Running MRP, planned orders, firming and releasing |
| **Accounting** | Chart of accounts, journal entries, reports |

## Verification Checklist

✅ **Backend running:** http://127.0.0.1:8000 shows "FilaOps API is running"
✅ **Frontend running:** http://localhost:5173 loads the application
✅ **Database connected:** No connection errors in backend terminal
✅ **Admin account created:** You can log in
✅ **Example data seeded:** (optional) Items and materials visible in UI
✅ **First sales order created:** Order appears in Sales Orders list

## Common Issues

### "Module not found" errors (Backend)

**Problem:** Missing Python dependencies

**Solution:**
```bash
cd backend
.\venv\Scripts\Activate
pip install -r requirements.txt
```

### "Cannot connect to database" error

**Problem:** PostgreSQL not running or wrong credentials in `.env`

**Solution:**
- Check PostgreSQL is running: `psql -U postgres -c "SELECT version();"`
- Verify DATABASE_URL in `backend/.env` matches your PostgreSQL credentials
- Ensure database `filaops` exists: `psql -U postgres -c "CREATE DATABASE filaops;"`

### Frontend shows "Network Error"

**Problem:** Backend not running or CORS misconfiguration

**Solution:**
- Ensure backend is running on http://127.0.0.1:8000
- Check `backend/.env` has `CORS_ORIGINS=http://localhost:5173`
- Restart backend after changing `.env`

### "Setup already complete" when trying to seed data

**Problem:** The `/setup/initial-admin` endpoint is disabled after first user is created

**Solution:** This is expected. The seed data endpoint is at `/setup/seed-example-data` and requires admin authentication (see "Seed Example Data" section above).

### Migrations fail with "relation already exists"

**Problem:** Database schema conflicts from previous installation

**Solution:**
```bash
# Drop and recreate database (⚠️ loses all data!)
psql -U postgres -c "DROP DATABASE filaops;"
psql -U postgres -c "CREATE DATABASE filaops;"

# Re-run migrations
cd backend
alembic upgrade head
```

## Getting Help

- **Documentation:** See other guides in `docs/user-guide/`
- **API Reference:** `docs/API-REFERENCE.md`
- **Issues:** [GitHub Issues](https://github.com/Blb3D/filaops/issues)
- **Contributing:** See `CONTRIBUTING.md`

## Development vs. Production

This guide covers **development setup**. For production deployment:

- Use a production-grade WSGI server (Gunicorn, uWSGI)
- Serve frontend as static build (`npm run build`)
- Use a reverse proxy (Nginx, Caddy)
- Enable HTTPS
- Use environment-specific `.env` files
- Set strong `SECRET_KEY` and `DATABASE_URL`
- Configure backups for PostgreSQL

See deployment guides (coming soon) for production setup.

---

**🎉 Congratulations!** You've successfully installed FilaOps and created your first sales order. Explore the other modules and see the power of an ERP built for 3D printing.
