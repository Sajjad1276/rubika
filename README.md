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
- Operational Rubika user-bot sessions must live on persistent storage. Mount a Railway Volume at `/data` and set `RUBIKA_SESSION_DIR=/data/sessions`.

## Dynamic List accounts

List operational accounts are **not static configuration**. They are database records and can change while the network is running.

- A List can receive a new operational account.
- An active account can be deactivated.
- A removed account is disconnected automatically.
- A newly activated account is connected automatically.
- If the session assigned to an active account changes, the old live client is closed and the new session is connected.
- The reconciliation loop runs every `LIST_ACCOUNT_SYNC_SECONDS` seconds, defaulting to 30.
- Publication only uses accounts that are both active in the database and currently connected.

This means adding or removing List accounts does not require restarting the Railway service.

## Implemented layers

- Async SQLAlchemy persistence with PostgreSQL/SQLite support
- MAXRubika transport and bot adapter
- Central roles and permissions
- Persistent per-bot conversation state
- Unified self-registration/admin-recruitment workflow
- Channel permission verification gate
- Monotonic per-list channel codes
- Campaign and campaign-target models
- Per-list pricing rules
- Advertising order and quote workflow
- Payment abstraction and settlement primitives
- Earnings ledger primitives
- Deterministic one-minute rotation planner
- Idempotent publication target states
- Retention-window monitoring
- Three-strike early-deletion enforcement
- Tasks, violations and audit history
- Dynamic operational List-account lifecycle
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
OWNER_USERNAME=<Rubika owner username>
ADMIN_USERNAME=<Rubika admin username>
RUBIKA_SESSION_DIR=/data/sessions
LIST_ACCOUNT_SYNC_SECONDS=30
```

`OWNER_ID` is retained only as a legacy compatibility setting and is not used for owner/admin authorization.

Never commit real Rubika tokens or production credentials.

## Railway session storage

Create a persistent Railway Volume and mount it at `/data`. Store each operational account's MAXRubika session under `/data/sessions` and save that path in the List account's `session_ref`.

Do not store session files in the Git repository or rely on the container's ephemeral filesystem.

## Database migrations

The application initializes missing tables on startup for a fresh database. Alembic migrations are also included for schema evolution. For a production database that already contains data, run the appropriate Alembic migrations before deploying code that requires a newer schema.
