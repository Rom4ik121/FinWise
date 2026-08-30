# База данных

## SQLite

SQLAlchemy 2.0, WAL, `PRAGMA foreign_keys=ON`.

Путь `AppConfig.db_path`:

| Платформа | Каталог |
|---|---|
| Windows | `%LOCALAPPDATA%\finanse\finanse\` |
| iOS | `~/Library/Application Support/finanse` |
| Android | `~/finanse` (песочница приложения) |

**Runtime:** `init_db()` =

1. `create_all` + `_apply_sqlite_column_patches` (старые файлы без Alembic)
2. `_ensure_sqlite_indexes` — идемпотентные составные индексы под горячие фильтры
3. best-effort `alembic upgrade head` (предупреждение в лог, если цепочка сломана)

`reset_engine()` — после restore и в тестах.

Опционально для разработчиков: `python scripts/migrate.py` / Alembic upgrade.

## Индексы (производительность)

Создаются при старте (`lib/core/database.py` → `_ensure_sqlite_indexes`) и миграцией **0016**:

| Индекс | Назначение |
|---|---|
| `ix_transactions_date_desc` | лента / аналитика по дате |
| `ix_transactions_account_date` | счёт + история |
| `ix_transactions_type_date` | доход/расход за период |
| `ix_transactions_category_date` | бюджеты / категории |
| `ix_transactions_type_category_date` | бюджетный месяц (type+category+date) |
| `ix_transactions_goal_date` / `debt_date` / `subscription_date` | unlink и связанные списки |
| `ix_transactions_transfer_id` / `subscription_id` | переводы / автосписания |
| `ix_budgets_month_year` / `category_month` | месячные лимиты |
| goals/debts/subscriptions status(+due/billing) | списки и напоминания |

**Теги** хранятся в JSON — фильтр `tags=` применяется в Python **до** `LIMIT`/`OFFSET`, чтобы пагинация была корректной (не через SQL `LIKE` по JSON).

## Запросы: границы и батчи

| Сценарий | Поведение |
|---|---|
| Аналитика период `all` | окно **5 лет** (`date_from = now − 5y`), бакеты месяц, chart ≤36 точек |
| Пересчёт бюджетов | **один** `list` расходов за месяц → агрегация по категориям; RateBook из кэша |
| Удаление цели | `clear_goal_links` — один SQL `UPDATE … SET goal_id=NULL` (credit amount сохраняется) |
| FX | `lib/domain/services/rate_cache.py` TTL ~90s; `invalidate_rate_book_cache()` после обновления курсов |

## Таблицы (`lib/infrastructure/db_models.py`)

**accounts** — name, currency, balance, initial_balance, icon, color, is_active, include_in_total, created_at.

**debts** — counterparty, amount, remaining_amount, currency, direction, status, interest_rate, due_date, started_at, comment, account_id, next_payment_date, next_payment_amount, accrue_interest, accrued_interest, last_interest_accrued_at, created_at, updated_at.  
Транзакции и подписки: `ON DELETE CASCADE`.

**transactions** — account_id, amount, category, tags JSON, date, comment, type,
currency, goal_id (SET NULL), debt_id (SET NULL), subscription_id (SET NULL),
goal/debt_credit_amount, transfer_id, transfer_peer_account_id, items JSON, timestamps.

**goals** — target/current, currency, deadline, priority, category_link, status,
is_completed, cached_projection JSON.

**subscriptions** — amount, account_id, category, periodicity, custom_interval_days,
start/end, max_payments, payments_made, next_billing_date, status, auto_charge.

**currencies** — code PK, names, symbol, is_crypto.

**exchange_rates** — base, quote, rate Numeric(24,12), UNIQUE(base, quote).

**categories** — name UNIQUE, icon, color, kind, is_system, is_active.

**settings** — id=`default`, default_currency, theme, **ui_style**, language,
exchange interval, флаги уведомлений, reminder_time/days,
check_balance_before_subscription, budget_alerts, pin_hash/salt, biometric_enabled.

**budgets** — category_id FK→categories.name (CASCADE), month, year, amount_limit,
spent, last_alert_level, created_at, updated_at, UNIQUE(category_id, month, year).

**exchange_connections** — account_id UNIQUE, provider, credentials_encrypted,
last_sync_at, last_error, holdings_json.

## Alembic (`migrations/versions/`)

Идемпотентные ревизии (`render_as_batch=True`):

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
| 0011 | exchange_connections |
| 0012 | budgets.created_at / last_alert_level backfill |
| 0013 | transaction items |
| 0014 | account.include_in_total |
| 0015 | debt schedule / accrual |
| 0016 | composite indexes (goal/debt/subscription/type+category+date) |

`migrations/env.py` берёт URL из `AppConfig`.
`python scripts/migrate.py` — init + сид.
