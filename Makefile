.PHONY: db backend-install migrate seed api test frontend-install web lint fixtures

db:                ## Start PostgreSQL (Docker, port 5434)
	docker compose up -d db

backend-install:
	cd backend && uv sync

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python -m app.seed

api:               ## FastAPI on :8000 (OpenAPI docs at /docs)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

test:
	cd backend && uv run pytest
	cd frontend && npx tsc --noEmit && npm run lint

fixtures:          ## Regenerate SIMULATED ENTSO-E XML fixtures
	cd backend && uv run python scripts/generate_entsoe_fixtures.py

frontend-install:
	cd frontend && npm install

web:               ## Next.js on :3000
	cd frontend && npm run dev

lint:
	cd backend && uv run ruff check app tests scripts
	cd frontend && npm run lint
