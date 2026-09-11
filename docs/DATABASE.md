# База данных

## 1. SQLite

- SQLAlchemy **2.0**, режим **WAL**, `PRAGMA foreign_keys=ON`.
- Файл: `AppConfig.db_path` → `{data_dir}/finanse.db`.

### Каталог данных

| Платформа | Путь |
|-----------|------|
| Windows | `%LOCALAPPDATA%\finanse\finanse\` (через `platformdirs`) |
| iOS | `FLET_APP_STORAGE_*` / иначе `~/Library/Application Support/finanse` внутри sandbox |
| Android | Только **writable** sandbox: `FLET_APP_STORAGE_DATA`, `/data/user/0/com.finanse.app/files/finanse` и аналоги. **Не** произвольный `~/finanse` на корне `/data` (PermissionError) |

Рядом: `backups/` (в т.ч. `.fwbackup`), `exports/`, `logs/`. На desktop/Android — `.secret_box_key`; на iPhone ключ в Keychain (файл мигрируется и удаляется).

---

## 2. Инициализация (`lib/core/database.py`)

`init_db()`:

1. **`create_all`** + `_apply_sqlite_column_patches` — догоняет старые файлы без полной Alembic-истории.
2. **`_ensure_sqlite_indexes`** — идемпотентные составные индексы под горячие фильтры.
3. Best-effort **`alembic upgrade head`** against the opened DB URL (legacy revision `0002_reminder_time` → `0002`; if the chain still fails — warning in the log, the app continues on patches).

`reset_engine()` — после restore и в тестах.

Для разработчиков: `python scripts/migrate.py` (init + сид по необходимости).  
`migrations/env.py` берёт URL из `AppConfig`.

---

## 3. Индексы

Создаются при старте и закреплены миграцией **0016** (часть индексов).

| Индекс | Назначение |
|--------|------------|
| `ix_transactions_date_desc` | Лента / аналитика по дате |
| `ix_transactions_account_date` | История счёта |
| `ix_transactions_type_date` | Доход/расход за период |
| `ix_transactions_category_date` | Бюджеты / категории |
| `ix_transactions_type_category_date` | Бюджетный месяц |
| `ix_transactions_goal_date` / `debt_date` / `subscription_date` | Связанные списки и unlink |
| `ix_transactions_transfer_id` / `subscription_id` | Переводы / автосписания |
| `ix_budgets_month_year` / `category_month` | Месячные лимиты |
| goals / debts / subscriptions status (+ due / billing) | Списки и напоминания |

**Теги** в JSON: фильтр `tags=` — SQL `EXISTS (json_each(transactions.tags) …)` на каждый требуемый тег, затем `LIMIT`/`OFFSET`. FTS по тегам не используется для exact-tag filter (`csv-import` / `xfer_fee:uuid` ломаются токенизатором). Fallback на Python, если JSON1 недоступен.

---

## 4. Границы запросов и батчи

| Сценарий | Поведение |
|----------|-----------|
| Аналитика период `all` | Окно **5 лет** (`date_from = now − 5y`), бакеты месяц, chart ≤ 36 точек |
| Пересчёт бюджетов | Один `list` расходов за месяц → агрегация по категориям; RateBook из кэша |
| Удаление цели | `clear_goal_links` — один SQL `UPDATE … SET goal_id=NULL` (credit amount сохраняется) |
| FX | `rate_cache.py` TTL ≈ 90 с; инвалидация после обновления курсов / wipe / restore |

Подробнее — [PERFORMANCE.md](PERFORMANCE.md).

---

## 5. Таблицы (`db_models.py`)

### `accounts`

`name`, `currency`, `balance`, `initial_balance`, `icon`, `color`, `is_active`, `include_in_total`, `is_corporate`, `created_at`.

### `transactions`

`account_id`, `amount`, `category`, `tags` (JSON), `date`, `comment`, `type`, `currency`,  
`goal_id` / `debt_id` / `subscription_id` (SET NULL),  
`goal_credit_amount` / `debt_credit_amount`,  
`transfer_id`, `transfer_peer_account_id`,  
`items` (JSON позиций чека), `attachments` (JSON путей к фото в `media/`), timestamps.

### `goals`

`target_amount`, `current_amount`, `currency`, `deadline`, `priority`, `category_link`, `status`, `is_completed`, `cached_projection` (JSON).

### `debts`

`counterparty`, `amount`, `remaining_amount`, `currency`, `direction`, `status`,  
`interest_rate`, `due_date`, `started_at`, `comment`, `account_id`,  
`next_payment_date` / `next_payment_amount`,  
`accrue_interest`, `accrued_interest`, `last_interest_accrued_at`, schedule-поля, timestamps.  
Связанные транзакции/подписки: осторожно с `ON DELETE` (см. модели).

### `subscriptions`

`amount`, `account_id`, `category`, `periodicity`, `custom_interval_days`,  
`start` / `end`, `max_payments`, `payments_made`, `next_billing_date`, `status`, `auto_charge`.

### `currencies` / `exchange_rates`

Валюты: `code` PK, имена, `symbol`, `is_crypto`.  
Курсы: `base`, `quote`, `rate` Numeric(24,12), UNIQUE(base, quote), источник/время.

### `categories`

`name` + `account_id` UNIQUE (`account_id` пустая строка = личный ledger; UUID = корпоративный счёт),  
`icon`, `color`, `kind`, `is_system`, `is_active`.

### `settings` (строка `id=default`)

`default_currency`, `theme`, `ui_style`, `language`, `language_user_set`,
интервал курсов, флаги уведомлений, `reminder_time` / `reminder_days`,
`check_balance_before_subscription`, `budget_alerts`,
`pin_hash` / `pin_salt`, `biometric_enabled`,
**`dashboard_hide_chart`**, **`dashboard_chart_days`** (миграция **0017**),
**`tx_filters_json`**, **`budget_warn_pct`** (по умолчанию 80), **`budget_limit_pct`** (100) — миграция **0028**,
**`language_user_set`** (миграция **0029**: существующие установки DEFAULT 1, новые — 0 до выбора в Settings),
иконки/цвета целей·долгов·подписок и goal items (миграции **0018–0021**).
порог низкого баланса и др.

### `budgets`

`category_id` → имя категории (мягкая ссылка; CASCADE в use case), `month`, `year`, `amount_limit`, `spent`,  
`last_alert_level`, `account_id` (пустая строка = личный; UUID = корпоративный счёт), timestamps,  
UNIQUE(category_id, month, year, account_id).

### `recurring_rules`

Шаблоны дохода/расхода (не подписки): `name`, `amount`, `currency`, `account_id`, `category`, `type`,  
`interval` / `interval_count`, `next_run`, `paused`, `skip_next`, `auto_create`, timestamps.

### `net_worth_snapshots`

Один снимок include-in-total баланса на UTC-день: `captured_on` UNIQUE, `amount`, `currency`, `captured_at`.

### `exchange_connections`

`account_id` UNIQUE, `provider`, `credentials_encrypted`, `last_sync_at`, `last_error`, `holdings_json`.

---

## 6. Alembic (`migrations/versions/`)

Идемпотентные ревизии (`render_as_batch=True`), цепочка **0001 → 0029**:

| Rev | Суть |
|-----|------|
| 0001 | Initial schema |
| 0002 | `reminder_time` (revision id **must** be `0002`; a filename leftover `0002_reminder_time` split the graph — `0003` depends on `0002`) |
| 0003 | `categories` |
| 0004 | Goals currency / status / projection |
| 0005 | Debt credit + indexes |
| 0006 | Flexible subscriptions |
| 0007 | `auto_charge` |
| 0008 | `budgets`, `budget_alerts` |
| 0009 | `transfer_id`, `transfer_peer_account_id` |
| 0010 | `settings.ui_style` |
| 0011 | `exchange_connections` |
| 0012 | budgets timestamps / `last_alert_level` |
| 0013 | `transaction.items` |
| 0014 | `account.include_in_total` |
| 0015 | Debt schedule / accrual |
| 0016 | Composite perf indexes |
| 0017 | `dashboard_hide_chart`, `dashboard_chart_days` |
| 0018 | Goal line items |
| 0019 | Goal enhancements (icon/color/audit) |
| 0020 | Debt enhancements (icon/color/audit) |
| 0021 | Subscription enhancements (icon/color/audit) |
| 0022 | `transactions_fts` FTS5 (category/comment/tags) |
| 0023 | Legacy unused onboarding flag columns on `settings` |
| 0024 | `accounts.is_corporate` |
| 0025 | `budgets.account_id` (corporate-scoped budgets) |
| 0026 | `transactions.attachments` JSON (receipt photos) |
| 0027 | `categories.account_id` + UNIQUE(name, account_id) |
| 0028 | `settings.tx_filters_json`, `budget_warn_pct`, `budget_limit_pct`; `recurring_rules`; `net_worth_snapshots`; FTS5 payee/amount |
| 0029 | `settings.language_user_set` (явный выбор языка vs авто с устройства) |

Head: **0029**. Fresh install: `init_db()` + column patches + FTS ensure; Alembic `upgrade head` targets the **same** SQLite URL as `AppConfig` (`migrations/env.py` honors `sqlalchemy.url`). Installs stamped with the obsolete id `0002_reminder_time` are rewritten to `0002` before upgrade. If upgrade still fails, a warning is logged and column patches keep the app running.

---

## 7. Бэкапы на диске

| Файл | Смысл |
|------|--------|
| `backups/finanse_YYYYMMDD_HHMMSS.db` | Ручной локальный снимок (timestamp) |
| `backups/finanse_YYYYMMDD_HHMMSS.fwbackup` | Share/restore бандл (AES-GCM zip: db + ключ + media) |
| `backups/finanse_daily.db` | Ежедневный rolling-снимок (overwrite раз в сутки) |
| `backups/finanse_daily.day` | Штамп локального дня последней daily-записи |

---

## 8. Связанные документы

- Слои — [ARCHITECTURE.md](ARCHITECTURE.md)  
- Репозитории — [INFRASTRUCTURE.md](INFRASTRUCTURE.md)  
- Производительность — [PERFORMANCE.md](PERFORMANCE.md)  
