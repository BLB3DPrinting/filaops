# FilaOps Frontend

React-based admin dashboard for FilaOps ERP.

## Tech Stack

- **React 19** with Vite
- **Tailwind CSS** with custom neo-industrial dark theme
- **React Router** for navigation
- **Recharts** for data visualization

## Quick Start

```bash
npm install
npm run dev
```

Open <http://localhost:5173>

## Project Structure

```text
src/
├── components/     # Reusable UI components
├── hooks/          # Custom React hooks
├── lib/            # Utilities and API client
├── pages/          # Route components
│   └── admin/      # Admin dashboard pages
└── services/       # API service functions
```

## Environment Variables

Create `.env.local`:

```ini
VITE_API_URL=http://localhost:8000
```

## Building

```bash
npm run build
```
