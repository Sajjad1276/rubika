# Rubika Smart Advertising Network

A modular advertising-network platform for Rubika.

- Domain-first application core
- SQLAlchemy async persistence
- PostgreSQL in production, SQLite for local development
- Rubika/FastRub adapter isolated from business logic
- Explicit workflows for registration, operations, violations and earnings
- Secrets loaded from environment variables

## Run

```bash
cp .env.example .env
pip install -e .
python -m ad_network.main
```
