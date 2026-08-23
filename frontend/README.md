# Litestar Project - Frontend

The frontend is built with [React 18](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), [Vite](https://vitejs.dev/), [Tailwind CSS](https://tailwindcss.com/), [shadcn/ui](https://ui.shadcn.com/) patterns, and [@hey-api/client-fetch](https://heyapi.dev/).

## Requirements

* [Node.js](https://nodejs.org/) (version 20+) or containerized execution via [Podman](https://podman.io/) / [Docker](https://www.docker.com/).

## Quick Start

### Option 1: Full-Stack Container Mesh (Recommended)

From the project root directory, start the entire container stack:

```bash
make up
```

The frontend SPA is immediately available at `http://localhost:8000/` with hot module replacement (HMR) reverse-proxied through Traefik.

### Option 2: Local Vite Development Server

Run the frontend locally against a running backend instance:

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173/` in your browser.

## Generating the TypeScript Client

The frontend client SDK is automatically compiled from the backend's OpenAPI 3.1 schema using `@hey-api/openapi-ts`.

### Automatically via Makefile

From the repository root directory, run:

```bash
make frontend-sync
```

This exports the latest OpenAPI specification to `frontend/openapi.json` and regenerates all typed bindings in `frontend/src/client/`.

### Verifying Zero Schema Drift

To ensure frontend bindings are always synchronized in CI/CD quality gates:

```bash
make check-client-drift
```

### Manual Generation

From the `frontend/` directory:

```bash
npm run generate-client
```

## Production Build

To test and compile the production bundle:

```bash
# Via root Makefile
make frontend-build

# Or directly from frontend/
cd frontend
npm run build
```

Production build output is emitted to `frontend/dist/`.

## Tailwind CSS & Theme Configuration

* **Theme Switching:** Supports dark mode, light mode, and system preference via `frontend/src/hooks/useTheme.tsx`.
* **Theme Variables:** Modern CSS variables defined in `frontend/src/index.css` following shadcn/ui palette standards (primary, secondary, destructive, muted, accent, background, foreground).
* **Utility Styling:** Tailwind CSS configured in `frontend/tailwind.config.js` with `tailwindcss-animate` and CSS variables integration.

## Environment Variables & Remote API

| Variable | Description | Default |
| :--- | :--- | :--- |
| `VITE_API_URL` | Base URL for remote backend API (leave empty for same-origin proxying) | `""` |
| `VITE_INITIAL_ADMIN_EMAIL` | Default email populated in the development login form | `admin@platform.internal` |
| `VITE_INITIAL_ADMIN_PASSWORD` | Default password populated in the development login form | `AdminSecurePassword2026!` |

To connect to a remote backend API during local Vite development:

```env
VITE_API_URL=https://api.platform.example.com
```

## Code Structure

```
frontend/
├── public/                 # Static assets, SVG logos, favicons
├── openapi.json            # Exported backend OpenAPI 3.1 specification
├── src/
│   ├── client/             # Auto-generated @hey-api TypeScript fetch client
│   │   ├── client.gen.ts   # Configured API client instance
│   │   ├── sdk.gen.ts      # Typed endpoint SDK functions
│   │   └── types.gen.ts    # TypeScript interface schemas
│   ├── components/
│   │   ├── common/         # AuthLayout, Logo, Appearance, ErrorBoundary, Footer
│   │   ├── layout/         # AppShell, TopNavbar, Sidebar
│   │   └── ui/             # Reusable UI primitives (Button, Input, Card, Modal, Badge)
│   ├── features/
│   │   ├── auth/           # LoginForm, AuthContext provider, authentication state
│   │   ├── dashboard/      # MetricsOverviewCards, SystemHealthCard, TelemetryStream
│   │   └── users/          # UsersDataTable, AddUser, EditUser, DeleteUser modals
│   ├── hooks/              # Custom React hooks (useAuth, useTheme)
│   ├── lib/                # Shared utilities, classnames (cn), api error interceptor
│   ├── pages/              # Top-level view components (LoginPage, DashboardPage, UsersPage, SettingsPage)
│   ├── App.tsx             # Root application router and shell container
│   └── main.tsx            # React DOM mounting entrypoint
├── package.json            # Node.js dependencies & scripts
├── tailwind.config.js      # Tailwind CSS theme configuration
└── vite.config.ts          # Vite build and dev-server configuration
```
