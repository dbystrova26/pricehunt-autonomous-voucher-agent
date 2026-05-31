.PHONY: setup setup-backend setup-frontend dev backend frontend test lint clean help

# ── Paths ─────────────────────────────────────────────────────────────────────
VENV        = backend/.venv
PYTHON      = $(VENV)/bin/python
PIP         = $(VENV)/bin/pip
UVICORN     = $(VENV)/bin/uvicorn
PYTEST      = $(VENV)/bin/pytest

# ── Default target ────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Pricehunt — dev commands"
	@echo ""
	@echo "  make setup       Create venv, install all deps, install Chromium"
	@echo "  make dev         Start backend + frontend in parallel"
	@echo "  make backend     Start backend only (port 8000)"
	@echo "  make frontend    Start frontend only (port 5173)"
	@echo "  make test        Run pytest inside the venv"
	@echo "  make lint        Run ruff linter on backend"
	@echo "  make clean       Remove .venv and node_modules"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
setup: setup-backend setup-frontend
	@echo ""
	@echo "✅  Setup complete."
	@echo "    Copy backend/.env.example → backend/.env and fill in your API keys."
	@echo "    Then run: make dev"
	@echo ""

setup-backend:
	@echo "→ Creating Python virtual environment..."
	python3 -m venv $(VENV)
	@echo "→ Installing Python dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt
	@echo "→ Installing Playwright Chromium browser..."
	$(PYTHON) -m playwright install chromium
	@if [ ! -f backend/.env ]; then \
		cp backend/.env.example backend/.env; \
		echo "→ Created backend/.env from .env.example — fill in your API keys"; \
	fi

setup-frontend:
	@echo "→ Installing frontend dependencies..."
	cd frontend && npm install
	@if [ ! -f frontend/.env ]; then \
		cp frontend/.env.example frontend/.env; \
		echo "→ Created frontend/.env from .env.example"; \
	fi

# ── Dev servers ───────────────────────────────────────────────────────────────
dev:
	@echo "→ Starting backend on :8000 and frontend on :5173"
	@$(MAKE) backend & $(MAKE) frontend

backend:
	cd backend && ../$(UVICORN) main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

# ── Test ──────────────────────────────────────────────────────────────────────
test:
	cd backend && ../$(PYTEST) tests/ -v

# ── Lint ──────────────────────────────────────────────────────────────────────
lint:
	$(VENV)/bin/ruff check backend/

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	@echo "→ Removing virtual environment..."
	rm -rf $(VENV)
	@echo "→ Removing frontend node_modules..."
	rm -rf frontend/node_modules
	@echo "✅  Clean complete. Run make setup to start fresh."
