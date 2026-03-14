.PHONY: help install dev test lint docker-up docker-down

help:
	@echo "SenseMap / Living GraphRAG"
	@echo ""
	@echo "  make install    Install dependencies (Python + Node)"
	@echo "  make dev        Run dev servers (API + web)"
	@echo "  make test       Run tests"
	@echo "  make lint       Run linters"
	@echo "  make docker-up  Start Docker stack (Neo4j, etc.)"
	@echo "  make docker-down Stop Docker stack"

install:
	pip install -e ".[dev]"
	cd apps/web && npm install
	cd apps/api && pip install -r requirements.txt 2>/dev/null || true

dev:
	@echo "Run API: cd apps/api && uvicorn main:app --reload"
	@echo "Run Web: cd apps/web && npm run dev"

test:
	pytest tests/ -v
	cd apps/web && npm run test 2>/dev/null || true

lint:
	ruff check .
	cd apps/web && npm run lint 2>/dev/null || true

docker-up:
	docker compose up -d

docker-down:
	docker compose down
