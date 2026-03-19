# Installation & Setup

> Get FilaOps running on your computer in about 15 minutes.

## What You'll Learn

- How to install the required software
- How to set up the database
- How to configure and start FilaOps
- How to verify everything is working

## Prerequisites

You need the following software installed before you begin:

| Software | Minimum Version | Purpose |
|----------|----------------|---------|
| **Python** | 3.11 or newer | Runs the backend server |
| **Node.js** | 18 or newer | Builds the frontend interface |
| **PostgreSQL** | 15 or newer | Stores all your data |
| **Git** | 2.0 or newer | Downloads the source code |

!!! warning "PostgreSQL Required"
    FilaOps requires PostgreSQL. It uses PostgreSQL-specific features like JSONB columns and array types, so SQLite or MySQL will not work.

**Download links:**

- Python: [python.org/downloads](https://www.python.org/downloads/)
- Node.js: [nodejs.org](https://nodejs.org/)
- PostgreSQL: [postgresql.org/download](https://www.postgresql.org/download/)
- Git: [git-scm.com/downloads](https://git-scm.com/downloads/)

## Step 1: Download FilaOps

Open a terminal and clone the repository:

```bash
git clone https://github.com/Blb3D/filaops.git
cd filaops
```

## Step 2: Create the Database

Connect to PostgreSQL and create a new database:

=== "Using psql (command line)"

    ```bash
    psql -U postgres
    ```

    Then in the psql prompt:

    ```sql
    CREATE DATABASE filaops;
    \q
    ```

=== "Using pgAdmin (GUI)"

    1. Open pgAdmin and connect to your PostgreSQL server
    2. Right-click **Databases** and choose **Create > Database**
    3. Name it `filaops` and click **Save**

## Step 3: Configure the Backend

Create your environment file:

```bash
cd backend
```

Create a file named `.env` in the `backend/` directory with the following contents:

```ini
# Database — change the password to match your PostgreSQL setup
DATABASE_URL=postgresql+psycopg://postgres:your_password@localhost:5432/filaops

# Security — generate a unique key for your installation
SECRET_KEY=change-this-to-a-random-string
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=43200

# Environment
ENVIRONMENT=development

# Frontend URL (for CORS)
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

!!! tip "Generate a secure secret key"
    For production use, generate a proper random key:

    === "Linux / Mac"

        ```bash
        openssl rand -hex 32
        ```

    === "Python (any platform)"

        ```bash
        python -c "import secrets; print(secrets.token_hex(32))"
        ```

    Copy the output and paste it as your `SECRET_KEY` value.

**Important:** Replace `your_password` with your actual PostgreSQL password.

## Step 4: Install Backend Dependencies

```bash
# Make sure you're in the backend/ directory
cd backend

# Create a Python virtual environment
python -m venv venv

# Activate it
# On Windows:
.\venv\Scripts\Activate
# On Linux/Mac:
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt

# Set up the database tables
alembic upgrade head
```

You should see a series of migration messages. The last line will look like:

```
INFO  [alembic.runtime.migration] Running upgrade ... -> ..., [migration name]
```

!!! warning "If migrations fail"
    If you see errors about relations already existing, your database may have leftover tables from a previous attempt. See [Troubleshooting](troubleshooting.md) for how to reset.

## Step 5: Install Frontend Dependencies

Open a **second terminal window** (keep the backend terminal open):

```bash
cd frontend
npm install
```

## Step 6: Start FilaOps

You need two terminal windows running at the same time.

**Terminal 1 — Backend:**

```bash
cd backend
.\venv\Scripts\Activate    # Windows
# source venv/bin/activate  # Linux/Mac
uvicorn app.main:app --reload
```

You should see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

**Terminal 2 — Frontend:**

```bash
cd frontend
npm run dev
```

You should see:

```
VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
```

## Step 7: Verify It Works

Open your browser and go to **http://localhost:5173**. On a fresh database (no users), FilaOps automatically redirects to the **Setup Wizard** where you create your admin account and optionally load example data.

**Verification checklist:**

- [ ] Backend responds at http://127.0.0.1:8000 (shows "FilaOps API is running")
- [ ] Frontend loads at http://localhost:5173
- [ ] No database connection errors in the backend terminal
- [ ] The setup wizard appears (if this is a fresh installation)

If all four checks pass, FilaOps is installed and ready to use.

!!! note "Setup wizard only appears once"
    The setup wizard is shown only when **zero users** exist in the database. Once you create an admin account, the wizard is permanently disabled and you are redirected to the login page. For details on the full setup flow and password reset behavior, see the [First-Run Setup Guide](../FIRST-RUN-SETUP.md).

## Docker Alternative

If you prefer Docker, you can run FilaOps with Docker Compose:

```bash
git clone https://github.com/Blb3D/filaops.git
cd filaops
cp backend/.env.example .env    # Edit with your settings
docker compose up -d
```

Open **http://localhost** to access FilaOps.

For full Docker deployment details, see the [Deployment Guide](../deployment/index.md).

## Development vs. Production

This guide covers **development setup** — running FilaOps locally for testing or small-scale use. For a production deployment with HTTPS, proper backups, and reverse proxy, see the [Deployment Guide](../deployment/index.md).

## What's Next?

Now that FilaOps is running, head to [Your First Day](first-day.md) to create your admin account, load sample data, and take a tour of the system.

## Quick Reference

| Task | How |
|------|-----|
| Start the backend | `cd backend && uvicorn app.main:app --reload` |
| Start the frontend | `cd frontend && npm run dev` |
| Run database migrations | `cd backend && alembic upgrade head` |
| Check backend health | Visit http://127.0.0.1:8000 |
| Access the application | Visit http://localhost:5173 |
| Stop either server | Press ++ctrl+c++ in its terminal |
