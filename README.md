# Rubika Smart Advertising Network

A modular advertising-network platform for Rubika. This is a clean rebuild of the previous bot and is designed to operate entirely through Rubika bots.

## Interface architecture

There is no web panel.

- **User Bot:** channel registration, ad requests, pricing, order tracking and support.
- **Admin Bot:** list operations, recruitment, channel verification, publishing tasks, violations and earnings.
- **Owner Bot:** network management, lists, roles, campaigns, pricing, audit and module configuration.
- **Supervisor:** uses the Owner Bot with supervisor permissions. No separate supervisor bot.

All three bots share the same application core and database. Bot handlers are interfaces only; business rules live in application/domain services.

## Deployment target

Railway is the production deployment target.

- PostgreSQL is the production database.
- SQLite is supported for local development.
- `railway.toml` starts the single process that runs all three bots concurrently.
- Production secrets are supplied through Railway environment variables.

## Current foundation

- Domain-first application core
- Async SQLAlchemy persistence
- PostgreSQL/SQLite support
- FastRub transport adapter
- Central role and permission resolution
- Persistent bot conversation state
- Unified self-registration/admin-recruitment workflow
- Channel permission verification gate before activation
- Monotonic per-list channel codes
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

1. Campaign/order model and pricing engine
2. Scheduled rotation and publication queue
3. Retention monitoring and automatic violation handling
4. Admin recruitment and performance tracking
5. Earnings and settlement
6. Owner/supervisor analytics and configurable bot modules
