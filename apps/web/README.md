# EvalOps Web Dashboard

Next.js 15 dashboard for EvalOps Studio.

## Environment variables

Create `apps/web/.env.local`:

```env
EVALOPS_API_BASE_URL=http://localhost:8000/v1
EVALOPS_DASHBOARD_BEARER_TOKEN=<jwt>
```

`EVALOPS_DASHBOARD_BEARER_TOKEN` is required for authenticated dashboard routes.

## Run

```bash
cd apps/web
npm install
npm run dev
```

## Main routes

- `/` - project entry
- `/o/[org]/p/[project]` - overview
- `/o/[org]/p/[project]/traces`
- `/o/[org]/p/[project]/traces/[trace]`
- `/o/[org]/p/[project]/evaluations`
- `/o/[org]/p/[project]/rubrics`
- `/o/[org]/p/[project]/prompts`
- `/o/[org]/p/[project]/datasets`
- `/o/[org]/p/[project]/experiments`
- `/o/[org]/p/[project]/keys`
- `/o/[org]/p/[project]/exports`
- `/docs`
- `/changelog`

## Build

```bash
npm run build
```
