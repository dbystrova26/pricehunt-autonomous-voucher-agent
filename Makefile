# ── OS note ───────────────────────────────────────────────────────────────────
# This Makefile works on Linux, macOS, and Windows WSL2.
# Windows native (cmd / PowerShell): run commands manually — see README.md.
# WSL2 is strongly recommended on Windows: wsl --install (PowerShell as admin)

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
	@echo "  make setup        Create venv, install Python deps, install Chromium"
	@echo "  make redis-start  Start Redis (auto-detects Linux / macOS / WSL2)"
	@echo "  make redis-check  Verify Redis is reachable"
	@echo "  make backend      Start FastAPI on port 8000"
	@echo "  make test         Run pytest inside the venv"
	@echo "  make lint         Run ruff linter on backend"
	@echo "  make clean        Remove .venv"
	@echo ""
	@echo "  Frontend: cd frontend && python3 -m http.server 5173"
	@echo "  (no npm needed — plain HTML file)"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
setup: setup-backend setup-frontend
	@echo ""
	@echo "✅  Setup complete."
	@echo "    1. Start Redis:       make redis-start"
	@echo "    2. Fill in API keys:  edit backend/.env"
	@echo "    3. Start servers:     make dev"
	@echo ""

# ── Redis helpers ─────────────────────────────────────────────────────────────
redis-start:
	@echo "→ Starting Redis..."
	@if command -v systemctl >/dev/null 2>&1; then \
		sudo systemctl start redis-server && echo "✅  Redis started via systemctl"; \
	elif command -v service >/dev/null 2>&1; then \
		sudo service redis-server start && echo "✅  Redis started via service (WSL2)"; \
	elif command -v brew >/dev/null 2>&1; then \
		brew services start redis && echo "✅  Redis started via Homebrew"; \
	elif command -v redis-server >/dev/null 2>&1; then \
		redis-server --daemonize yes && echo "✅  Redis started as daemon"; \
	else \
		echo "❌  Redis not found. See README.md for install instructions."; \
		exit 1; \
	fi

redis-check:
	@redis-cli ping 2>/dev/null && echo "✅  Redis is running" || echo "❌  Redis not reachable — run: make redis-start"


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

# Frontend needs no setup — it is a plain HTML file.
# Serve locally with: cd frontend && python3 -m http.server 5173

# ── Dev servers ───────────────────────────────────────────────────────────────
dev:
	@echo "→ Starting backend on :8000 and frontend on :5173"
	@$(MAKE) backend & $(MAKE) frontend
	@echo "   Backend: http://localhost:8000"
	@echo "   Frontend: http://localhost:5173 (plain HTML — no npm)"

backend:
	cd backend && ../$(UVICORN) main:app --reload --port 8000

frontend:
	@echo "→ Serving frontend on http://localhost:5173"
	cd frontend && python3 -m http.server 5173

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
	@echo "✅  Clean complete. Run make setup to start fresh."
