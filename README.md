# Rubika Smart Advertising Network

A modular advertising-network platform for Rubika. This repository is a clean rebuild of the previous bot, with the network model separated from the Rubika transport layer.

## Current foundation

- Domain-first application core
- SQLAlchemy async persistence
- PostgreSQL in production, SQLite for local development
- Rubika/FastRub adapter isolated from business logic
- Unified registration workflow for self-registration and admin recruitment
- Monotonic per-list channel codes that are not intentionally recycled
- Campaign and per-channel targeting model
- Retention-window and early-deletion policy primitives
- Tasks, violations and immutable audit history primitives
- Alembic wiring for schema migrations
- Secrets loaded from environment variables

## Architecture

```text
Rubika / FastRub
       |
   adapters
       |
 application services
       |
 domain + workflows
       |
 PostgreSQL / Redis / workers
       |
 owner / admin / supervisor interfaces
```

Rubika is treated as an adapter, not as the source of truth. The database owns channel registration, list membership, campaign targets, operational state and audit history.

## Run locally

```bash
cp .env.example .env
pip install -e .
python -m ad_network.main
```

For development dependencies:

```bash
pip install -e '.[dev]'
pytest
```

## Environment

See `.env.example`. Never commit a real Rubika token or other production credentials.

## Product direction

The next layers are the actual operational interfaces and workers: user registration wizard, admin task/recruitment workflow, owner controls, scheduled campaign publishing, retention verification, pricing/orders/earnings, supervisor tooling, and network analytics.
