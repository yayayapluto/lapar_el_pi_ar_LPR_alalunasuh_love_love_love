SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

PYTHON ?= python
PIP ?= $(PYTHON) -m pip
UVICORN ?= uvicorn
HOST ?= 0.0.0.0
PORT ?= 8000
IMAGE ?= lpr-service

.PHONY: help venv install dev prod test test-file docker-build docker-run monitoring-up monitoring-down

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*##"; printf "\nAvailable commands:\n"} /^[a-zA-Z0-9_-]+:.*##/ {printf "  %-16s %s\n", $$1, $$2} END {print ""}' $(MAKEFILE_LIST)

venv: ## Create virtual environment in ./venv
	$(PYTHON) -m venv venv

install: ## Install dependencies from requirements.txt
	$(PIP) install -r requirements.txt

dev: ## Run development server (loads .env via run.py)
	$(PYTHON) run.py

prod: ## Run production-like server with uvicorn
	$(UVICORN) app.main:app --host $(HOST) --port $(PORT)

test: ## Run all unit tests
	$(PYTHON) -m unittest discover tests -v

test-file: ## Run a single test module (usage: make test-file TEST=tests.test_metrics)
ifndef TEST
	$(error TEST is required. Example: make test-file TEST=tests.test_metrics)
endif
	$(PYTHON) -m unittest $(TEST) -v

docker-build: ## Build Docker image
	docker build -t $(IMAGE) .

docker-run: ## Run Docker container (expects .env file)
	docker run -p $(PORT):$(PORT) --env-file .env $(IMAGE)

monitoring-up: ## Start monitoring profile from parent repo root
	@if [ -f ../docker-compose.yml ] || [ -f ../compose.yml ]; then \
		cd .. && docker compose --profile monitoring up --build; \
	else \
		echo "No compose file found in parent directory. Run from project root manually."; \
		exit 1; \
	fi

monitoring-down: ## Stop monitoring profile from parent repo root
	@if [ -f ../docker-compose.yml ] || [ -f ../compose.yml ]; then \
		cd .. && docker compose --profile monitoring down; \
	else \
		echo "No compose file found in parent directory. Run from project root manually."; \
		exit 1; \
	fi
