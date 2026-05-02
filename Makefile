# BeerBeer dashboard — one-command operations.
#
# `make up`              start Postgres+Redis+Superset, seed warehouse
# `make build-dashboard` materialise dashboard from spec.yaml
# `make logs`            tail Superset logs
# `make down`            stop everything (preserves volumes)
# `make nuke`            stop + drop volumes (fresh slate)

SHELL := /usr/bin/env bash
COMPOSE ?= docker compose

include .env
export

.PHONY: up down nuke logs ps build-dashboard wait shell-pg

up:
	$(COMPOSE) up -d
	@$(MAKE) wait

wait:
	@echo ">>> waiting for Superset on $(SUPERSET_URL) ..."
	@until curl -fsS $(SUPERSET_URL)/health >/dev/null 2>&1; do sleep 2; done
	@echo "    ready."

build-dashboard:
	python3 -m pip install --quiet -r dashboard/requirements.txt
	python3 dashboard/build.py

logs:
	$(COMPOSE) logs -f --tail=200 superset

ps:
	$(COMPOSE) ps

down:
	$(COMPOSE) down

nuke:
	$(COMPOSE) down -v

shell-pg:
	$(COMPOSE) exec postgres psql -U $(POSTGRES_USER) -d beerbeer
