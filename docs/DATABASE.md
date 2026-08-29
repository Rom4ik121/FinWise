# База данных

## SQLite

SQLAlchemy 2.0, WAL, `PRAGMA foreign_keys=ON`.

Путь `AppConfig.db_path`:

| Платформа | Каталог |
|---|---|
| Windows | `%LOCALAPPDATA%\finanse\finanse\` |
| iOS | `~/Library/Application Support/finanse` |
| Android | `~/finanse` (песочница приложения) |

`init_db()` — `create_all` + `_apply_sqlite_column_patches` для старых файлов.
`reset_engine()` — после restore и в тестах.

## Таблицы (`lib/infrastructure/db_models.py`)

**accounts** — name, currency, balance, initial_balance, icon, color, is_active, created_at.  
Транзакции и подписки: `ON DELETE CASCADE`.

**transactions** — account_id, amount, category, tags JSON, date, comment, type,
currency, goal_id (SET NULL), debt_id (SET NULL), subscription_id (SET NULL),
goal/debt_credit_amount, transfer_id, transfer_peer_account_id, timestamps.

**goals** — target/current, currency, deadline, priority, category_link, status,
is_completed, cached_projection JSON.

**debts** — counterparty, amount/remaining, currency, direction, status,
interest_rate, due_date, started_at.

**subscriptions** — amount, account_id, category, periodicity, custom_interval_days,
start/end, max_payments, payments_made, next_billing_date, status, auto_charge.

**currencies** — code PK, names, symbol, is_crypto.

**exchange_rates** — base, quote, rate Numeric(24,12), UNIQUE(base, quote).

**categories** — name UNIQUE, icon, color, kind, is_system, is_active.

**settings** — id=`default`, default_currency, theme, **ui_style**, language,
exchange interval, флаги уведомлений, reminder_time/days,
check_balance_before_subscription, budget_alerts, pin_hash/salt, biometric_enabled.

**budgets** — category_id FK→categories.name (CASCADE), month, year, amount_limit,
spent, last_alert_level, UNIQUE(category_id, month, year).

## Alembic (`migrations/versions/`)

10 идемпотентных ревизий (`render_as_batch=True`):

| Ревизия | Суть |
|---|---|
| 0001 | Базовая схема |
| 0002 | settings.reminder_time |
| 0003 | categories |
| 0004 | goals currency/status/projection; goal_credit_amount |
| 0005 | debt_credit_amount, индексы долгов |
| 0006 | гибкие подписки, subscription_id, reminder_days |
| 0007 | auto_charge |
| 0008 | budgets, budget_alerts |
| 0009 | transfer_id, transfer_peer_account_id |
| 0010 | settings.ui_style |

`migrations/env.py` берёт URL из `AppConfig`.
`python scripts/migrate.py` — init + сид.
