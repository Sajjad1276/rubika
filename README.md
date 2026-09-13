# Rubika Smart Advertising Network

A modular advertising-network platform for Rubika, designed to operate entirely through Rubika bots.

## Interface architecture

There is no web panel.

- **User Bot:** channel registration, ad requests, quotes and order tracking.
- **Admin Bot:** list operations, recruitment, verification, publication tasks, violations and earnings.
- **Owner Bot:** network management, lists, roles, campaigns, pricing, audit and module configuration.
- **Supervisor:** uses the Owner Bot with supervisor permissions. No separate supervisor bot.

All three bots share one application core and database. Bot handlers are interfaces only; business rules live in application/domain services.

## Deployment target

Railway is the production deployment target.

- PostgreSQL is used in production.
- SQLite is supported for local development.
- `railway.toml` starts the single process containing all three bots.
- Production secrets are supplied through Railway environment variables.

## Implemented layers

- Async SQLAlchemy persistence with PostgreSQL/SQLite support
- FastRub transport adapter
- Central roles and permissions
- Persistent per-bot conversation state
- Unified self-registration/admin-recruitment workflow
- Channel permission verification gate
- Monotonic per-list channel codes
- Campaign and campaign-target models
- Per-list pricing rules
- Advertising order and quote workflow
- Earnings ledger primitives
- Deterministic one-minute rotation planner
- Idempotent publication target states
- Retention-window monitoring
- Three-strike early-deletion enforcement
- Tasks, violations and audit history
- Railway deployment configuration

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

## Required production variables

```text
DATABASE_URL=<Railway PostgreSQL URL>
USER_BOT_TOKEN=<user bot token>
ADMIN_BOT_TOKEN=<admin bot token>
OWNER_BOT_TOKEN=<owner bot token>
OWNER_ID=<Rubika owner user id>
```

Never commit real Rubika tokens or production credentials.

## Next implementation layers

1. Real Rubika permission/member-count verification through the gateway
2. Per-list account/session management and safe publication worker
3. Admin recruitment CRM and KPI tracking
4. Payment provider abstraction and settlement workflow
5. Owner/supervisor analytics and configurable bot modules
6. Integration tests against mocked FastRub responses
