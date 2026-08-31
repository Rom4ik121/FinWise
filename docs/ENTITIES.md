# Доменные сущности

Все модели — **Pydantic v2** в `lib/domain/entities/`. Persistence-слой маппит их на SQLAlchemy (`lib/infrastructure/db_models.py`).

---

## Деньги и коды валют

### `money.py`

- **`quantize_money(amount, currency)`** — фиат обычно до 2 знаков; известные криптокоды — до 8.
- Используется во всех записях операций и пересчётах баланса.

### `currency_codes.py`

- Нормализация кода валюты (регистр, алиасы).
- Хелперы «это крипта?» для формата отображения.

---

## Account (`account.py`)

Счёт пользователя.

| Поле | Смысл |
|------|--------|
| `id` | UUID-строка |
| `name` | Название |
| `currency` | Код валюты счёта |
| `balance` | Текущий баланс |
| `initial_balance` | Стартовый баланс (до операций) |
| `icon`, `color` | Оформление |
| `is_active` | Активен ли в списках |
| `include_in_total` | Участвует ли в «общем балансе» на главной |

Биржевой счёт дополнительно связан с `ExchangeConnection` (отдельная сущность).

---

## Transaction (`transaction.py`)

Одна операция по счёту.

| Поле | Смысл |
|------|--------|
| `type` | `income` / `expense` (`TransactionType`) |
| `amount`, `currency` | Сумма и валюта строки |
| `account_id` | Счёт |
| `category` | Имя категории (строка) |
| `comment`, `tags` | Комментарий и теги |
| `date` | Дата/время (UTC-aware) |
| `goal_id`, `debt_id`, `subscription_id` | Опциональные связи |
| `goal_credit_amount`, `debt_credit_amount` | Суммы вклада в цель/долг (с учётом FX) |
| `transfer_id` | Общий id пары перевода |
| `transfer_peer_account_id` | Счёт второй ноги |
| `items` | Список `TransactionItem` (позиции чека) |

**`TransactionItem`:** `name`, `category`, `amount` — сумма позиций должна согласовываться с итогом операции.

Свойство **`is_transfer`** — true, если задан `transfer_id`.

---

## Category (`category.py`)

| Поле | Смысл |
|------|--------|
| `name` | Уникальное отображаемое имя |
| `kind` | `income` / `expense` / `both` (`CategoryKind`) |
| `icon`, `color` | UI |

Системные имена (перевод, комиссия, накопление) задаются в конфиге/коде use cases.

---

## Currency / ExchangeRate (`currency.py`)

- **`Currency`** — код, имена (ru/en), символ, флаг крипты.
- **`ExchangeRate`** — пара `base`/`quote`, курс, источник, время обновления.

Каталог при старте сидится из `assets/data/currencies.json`.

---

## Goal (`goal.py`)

Цель накопления.

| Поле | Смысл |
|------|--------|
| `name`, `target_amount`, `currency` | Цель |
| `current_amount` | Накоплено |
| `status` | active / completed / archived |
| `deadline`, `priority` | Опционально |
| `category_link` | По умолчанию категория накопления |
| `cached_projection` | Кэш прогноза |

Пополнения идут через связанные транзакции (`goal_id`), не прямым «магическим» изменением баланса цели в обход ledger.

---

## Debt (`debt.py`)

| Поле | Смысл |
|------|--------|
| `direction` | мне должны / я должен |
| `status` | open / paid / … |
| `principal`, `currency`, `remaining` | Суммы |
| `counterparty` | Контрагент |
| `interest_rate`, `schedule` | Проценты / график |
| `accrue_interest`, `accrued_interest` | Начисление |
| `account_id` | Предпочитаемый счёт для операций |
| `due_date` | Срок |

Платежи отражаются транзакциями с `debt_id`.

---

## Subscription (`subscription.py`)

Регулярный платёж.

| Поле | Смысл |
|------|--------|
| `name`, `amount`, `currency` | Платёж |
| `account_id` | Счёт списания |
| `periodicity` | day / week / month / year / … |
| `status` | active / paused / cancelled |
| `next_billing_date` | Следующее списание |
| `auto_charge` | Автосписание при due |
| `max_payments` / счётчики | Ограничение числа платежей |

---

## Budget (`budget.py`)

- **`Budget`** — лимит на категорию (или набор) за месяц/год, валюта базы.
- **`BudgetProgress`** — лимит, потрачено, остаток, доля (для UI).

Расходы без цели накопления двигают прогресс через `apply_expense_delta` в use cases бюджетов.

---

## AppSettings (`settings.py`)

Пользовательские настройки (сущность без PIN-хеша — хеш лежит в ORM `settings`):

| Поле | Смысл |
|------|--------|
| `default_currency` | Базовая валюта отчётов |
| `theme`, `ui_style`, `language` | Внешний вид и язык |
| `exchange_update_interval_minutes` | Как часто тянуть курсы |
| `notifications_enabled`, флаги reminder’ов | Пуши / in-app |
| `reminder_time`, `reminder_days` | Когда напоминать о подписках/долгах |
| `biometric_enabled` | Face ID вместе с PIN |
| `dashboard_hide_chart`, `dashboard_chart_days` | График на главной |
| `low_balance_threshold` | Опциональный порог |
| `check_balance_before_subscription` | Проверка баланса перед списанием |

---

## ExchangeConnection (`exchange_connection.py`)

Связка счёта с биржей:

| Поле | Смысл |
|------|--------|
| `account_id` | Локальный счёт |
| `provider` | id из каталога `exchanges.py` |
| `credentials_encrypted` | Зашифрованный blob ключей |
| `holdings_json` | Снимок активов |
| `last_sync_at`, `last_error` | Статус синка |

Провайдеры (фрагмент): Binance, Coinbase, OKX, Bybit, Kraken, KuCoin, Gate.io, Bitget, MEXC, BitMart, HTX, Hyperliquid, BitMEX, WOO, Crypto.com, Bitfinex, Bitstamp, BingX, HashKey, CEX.IO.

---

## Связанные документы

- Сценарии работы с сущностями — [USE_CASES.md](USE_CASES.md)  
- Таблицы БД — [DATABASE.md](DATABASE.md)  
