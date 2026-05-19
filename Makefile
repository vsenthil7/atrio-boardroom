# ATRIO Boardroom — top-level Makefile
# Goal: `make up` brings the whole stack online in <15 minutes from a clean clone.

.PHONY: help up down logs ps seed test test-backend test-frontend test-e2e \
        lint format clean migrate keys backend-shell db-shell coverage build

help:
	@echo "ATRIO Boardroom — common commands"
	@echo ""
	@echo "  make up               Start the full local stack (postgres, api, frontend, livekit, minio, mailhog)"
	@echo "  make down             Stop everything"
	@echo "  make logs             Tail logs for the API"
	@echo "  make ps               List running containers"
	@echo "  make seed             Seed demo tenant + agents + memory"
	@echo "  make migrate          Apply Alembic migrations"
	@echo "  make test             Run all backend and frontend tests"
	@echo "  make test-backend     Run pytest with coverage"
	@echo "  make test-frontend    Run vitest"
	@echo "  make test-e2e         Run Playwright E2E"
	@echo "  make coverage         Generate HTML coverage reports"
	@echo "  make lint             Lint backend (ruff, mypy) and frontend (eslint, tsc)"
	@echo "  make format           Auto-format (ruff, prettier)"
	@echo "  make keys             Generate local JWT keypair"
	@echo "  make backend-shell    Open a shell in the api container"
	@echo "  make db-shell         psql into the local Postgres"
	@echo "  make clean            Remove containers, volumes, build artefacts"
	@echo ""

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

up: keys
	docker compose -f docker/docker-compose.yml --env-file .env up -d --build
	@echo ""
	@echo "ATRIO is up. Frontend: http://localhost:5173  API: http://localhost:8000/api/v1/health"

down:
	docker compose -f docker/docker-compose.yml down

logs:
	docker compose -f docker/docker-compose.yml logs -f api

ps:
	docker compose -f docker/docker-compose.yml ps

build:
	docker compose -f docker/docker-compose.yml build

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

migrate:
	docker compose -f docker/docker-compose.yml exec api alembic upgrade head

seed:
	docker compose -f docker/docker-compose.yml exec api python -m app.scripts.seed_demo

db-shell:
	docker compose -f docker/docker-compose.yml exec postgres psql -U atrio -d atrio

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

test: test-backend test-frontend test-e2e

test-backend:
	cd backend && pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=85

test-frontend:
	cd frontend && npm run test -- --coverage

test-e2e:
	cd frontend && npx playwright test

coverage:
	cd backend && pytest --cov=app --cov-report=html
	cd frontend && npm run coverage
	@echo "Backend coverage: backend/htmlcov/index.html"
	@echo "Frontend coverage: frontend/coverage/index.html"

# ---------------------------------------------------------------------------
# Lint / format
# ---------------------------------------------------------------------------

lint:
	cd backend && ruff check app tests && mypy app
	cd frontend && npm run lint && npm run typecheck

format:
	cd backend && ruff format app tests && ruff check --fix app tests
	cd frontend && npm run format

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

keys:
	@mkdir -p secrets
	@test -f secrets/jwt_private.pem || (openssl genrsa -out secrets/jwt_private.pem 2048 && \
	   openssl rsa -in secrets/jwt_private.pem -pubout -out secrets/jwt_public.pem && \
	   echo "Generated JWT keypair under secrets/")

backend-shell:
	docker compose -f docker/docker-compose.yml exec api bash

clean:
	docker compose -f docker/docker-compose.yml down -v --remove-orphans
	rm -rf backend/htmlcov backend/.coverage backend/.pytest_cache frontend/coverage frontend/test-results
	find . -type d -name __pycache__ -exec rm -rf {} +

voice-sidecar:
	docker compose -f docker/docker-compose.yml --env-file .env --profile voice up -d voice-sidecar

openapi:
	cd backend && ATRIO_ENV=test DATABASE_URL=sqlite+aiosqlite:///:memory: \
	  ATRIO_MOCK_INFERENCE=true \
	  MODEL_REGISTRY_PATH=../config/models/atrio.yaml \
	  PROMPTS_DIR=../prompts \
	  python -c "import json; from app.main import create_app; \
	    json.dump(create_app().openapi(), open('../docs/openapi.json','w'), indent=2)"
	@echo "OpenAPI spec written to docs/openapi.json"
