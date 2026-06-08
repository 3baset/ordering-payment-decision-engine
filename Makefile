# ODA — Ordering Decisioning Agent
# Usage: make <target>
#
# Variables (override on command line):
#   DAYS=<n>       override simulation days  (make sim DAYS=30)
#   LIMIT=<n>      seed only first N orders  (make seed LIMIT=100)
#   TABLE=<name>   override DynamoDB table   (make seed TABLE=my-table)

.DEFAULT_GOAL := help
VENV          := .venv
PYTHON        := $(VENV)/bin/python3
SIM_DIR       := simulation_engine
DATA_DIR      := data
SIM_OUTPUT    := $(SIM_DIR)/output/tables

# ── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "ODA — Ordering Decisioning Agent"
	@echo ""
	@echo "  make setup        Install all dependencies"
	@echo "  make sim          Run simulation engine (8-12 min, ~3 GB output)"
	@echo "  make sample       Sample 100k total records from simulation output"
	@echo "  make dashboard    Launch Streamlit dashboard"
	@echo "  make test         Run all unit tests (28 tests)"
	@echo "  make seed         Seed Sample A into DynamoDB oda-orders"
	@echo "  make seed-smoke   Seed first 100 orders (smoke test)"
	@echo "  make deploy       CDK deploy OdaStack to AWS"
	@echo "  make teardown     Empty DynamoDB tables (keep stack)"
	@echo "  make clean        Remove simulation output and sampled data"
	@echo ""
	@echo "Variables: DAYS=<n>  LIMIT=<n>  TABLE=<name>"
	@echo ""

# ── Venv + Setup ──────────────────────────────────────────────────────────────
.PHONY: venv
venv:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@echo "Virtualenv ready at $(VENV)/"

.PHONY: setup
setup: venv
	$(PYTHON) -m pip install --upgrade pip --quiet
	$(PYTHON) -m pip install -r requirements.txt
	@echo ""
	@echo "Setup complete. Activate with: source $(VENV)/bin/activate"
	@echo "Run 'make sim' to generate synthetic data."

# ── Simulation ────────────────────────────────────────────────────────────────
.PHONY: sim
sim:
	@echo "Running simulation engine (takes 8–12 minutes)…"
ifdef DAYS
	cd $(SIM_DIR) && $(PYTHON) simulation_runner.py --days $(DAYS)
else
	cd $(SIM_DIR) && $(PYTHON) simulation_runner.py
endif
	@echo "Simulation complete. Run 'make sample' next."

# ── Sampling ──────────────────────────────────────────────────────────────────
.PHONY: sample
sample:
	@echo "Sampling 100k total records across all tables…"
	$(PYTHON) -m data_sampler data_sampler/configs/last_90d.yaml
	@echo "Sample written to $(DATA_DIR)/. Run 'make seed' to load into DynamoDB."

# ── Dashboard ─────────────────────────────────────────────────────────────────
.PHONY: dashboard
dashboard:
	$(PYTHON) -m streamlit run sampler_dashboard.py

# ── Tests ─────────────────────────────────────────────────────────────────────
.PHONY: test
test:
	$(PYTHON) -m pytest tests/ -v

# ── AWS: seed ─────────────────────────────────────────────────────────────────
.PHONY: seed
seed:
ifdef LIMIT
	$(PYTHON) scripts/seed.py --limit $(LIMIT)
else
	$(PYTHON) scripts/seed.py
endif

.PHONY: seed-smoke
seed-smoke:
	$(PYTHON) scripts/seed.py --limit 100

# ── AWS: deploy ───────────────────────────────────────────────────────────────
.PHONY: deploy
deploy:
	cd infra && cdk deploy

.PHONY: deploy-diff
deploy-diff:
	cd infra && cdk diff

# ── Teardown ──────────────────────────────────────────────────────────────────
.PHONY: teardown
teardown:
	$(PYTHON) scripts/teardown.py

# ── Clean ─────────────────────────────────────────────────────────────────────
.PHONY: clean
clean:
	rm -rf $(SIM_DIR)/output $(DATA_DIR)/sample_a $(DATA_DIR)/sample_b $(DATA_DIR)/reference
	@echo "Cleaned simulation output and sampled data."
