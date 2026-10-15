# AI Business OS

A SaaS platform where a CEO onboards their company, hires specialised AI employees, grounds them in company
knowledge (RAG), tests them in simulations, approves their permissions and supervises their work through
evidence-backed reports. Requirements: [docs/SPEC.md](docs/SPEC.md). Progress: [docs/STATUS.md](docs/STATUS.md).

## Stack
FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 + pgvector · Redis · Next.js 16 · React 19 · Tailwind v4.

## Local setup
```powershell
docker compose up -d postgres redis
cd backend
py -3.12 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env          # optional overrides
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m abos.seed
.venv\Scripts\uvicorn abos.main:app --port 8470
# new terminal
cd frontend
npm install
npm run dev                     # http://localhost:3470
```
Dev login: `ceo@abos-dev.example.com` / `dev-password-change-me`. Verification and reset links are stored in the
`email_outbox` table (dev mailer never sends).

## Tests
- Backend: `cd backend; .venv\Scripts\pytest -q` and `.venv\Scripts\ruff check .`
- Frontend: `npm run lint`, `npm run typecheck`, `npm run build`
- Browser E2E (stack running): `cd frontend; npx playwright test`

## Docs
[Architecture](docs/ARCHITECTURE.md) · [Phases](docs/PHASES.md) · [Decisions](docs/DECISIONS.md) ·
[Status & session log](docs/STATUS.md) · [Security](docs/SECURITY.md) · [Operations & backups](docs/OPERATIONS.md) ·
[Deployment](docs/DEPLOYMENT.md) · RAG / agents / simulation / execution / reporting:
[RAG](docs/RAG.md), [AGENTS](docs/AGENTS.md), [SIMULATION](docs/SIMULATION.md), [EXECUTION](docs/EXECUTION.md),
[REPORTING](docs/REPORTING.md)
