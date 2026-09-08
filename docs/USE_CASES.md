# Use cases (бизнес-сценарии)

Use cases живут в `lib/domain/use_cases/`. Типичный контракт: класс с `async def execute(...)`.  
UI **не** пишет в ledger напрямую через репозитории для расходов/доходов, которые должны бить по бюджетам/целям — используется соответствующий use case.

---

## Транзакции — `transactions.py`

| Класс | Назначение |
|-------|------------|
| `AddTransactionUseCase` | Создать операцию, обновить баланс, применить цель/долг/бюджет |
| `UpdateTransactionUseCase` | Изменить; откатить старые side-effects и наложить новые |
| `DeleteTransactionUseCase` | Удалить; для перевода — обе ноги + связанную комиссию по тегу |
| `ListTransactionsUseCase` | Фильтры: счёт, даты, тип, теги, transfer, **`has_debt`**, limit/offset |
| `GetTransactionStatsUseCase` | Агрегаты для графиков |
| `TransferAccountsUseCase` | Перевод между счетами + опциональная комиссия |

Атомарные multi-step сценарии (add/update/delete, transfer, charge подписки и т.п.) оборачиваются в `lib/domain/unit_of_work.unit_of_work(session_factory)`.

Тяжёлые агрегаты и экспорт читают ledger через `transaction_paging` (страницы по 500, потолок 25 000), а не unbounded `list()`.

### Правила перевода

1. Нельзя перевод «сам в себя».
2. Сумма > 0; комиссия ≥ 0.
3. Создаются **две** операции с общим `transfer_id` (расход на источнике, доход на приёмнике).
4. При разной валюте — конвертация через `RateBook`; нет курса → ошибка.
5. Комиссия — **отдельный** расход «Комиссия» / тег fee на выбранном счёте комиссии (по умолчанию источник).
6. Ноги перевода нельзя править порознь (сумма/счета/тип) — только комментарий и подобные поля, либо удаление пары.

### Хелперы

- `make_fee_expense(...)` — собрать расход комиссии.
- Тег комиссии перевода: стабильный маркер по `transfer_id`.

---

## Счета — `accounts.py`

| Класс | Назначение |
|-------|------------|
| `CreateAccountUseCase` | Новый счёт |
| `UpdateAccountUseCase` | Обновление; смена валюты требует курсов и пересчёта |
| `DeleteAccountUseCase` | Удаление (с проверками) |
| `ListAccountsUseCase` | Список (active_only и т.д.) |
| `RecalculateAccountBalanceUseCase` | Пересчёт баланса из ledger |

Смена валюты счёта без курса — ошибка пользователю.

---

## Биржи — `exchange_sync.py`

| Класс | Назначение |
|-------|------------|
| `ConnectExchangeAccountUseCase` | Создать/обновить счёт + `ExchangeConnection`, зашифровать ключи |
| `SyncExchangeAccountUseCase` | Стянуть holdings/сделки через CCXT, импортировать операции, выставить баланс по снимку биржи |

Импортированные строки помечаются тегами синка; `last_error` хранит стабильное доменное сообщение.

- Неверный API-ключ → `Invalid exchange API credentials` → UI `error.exchange_bad_credentials` (без сырого JSON CCXT).
- Прочий сбой синка → `error.sync_failed` / дружелюбный snack.
- Auth-ошибки логируются warning **без** traceback spam.

---

## Цели — `goals.py`

CRUD цели, **вклад** со счёта (`contribute_to_goal`), проекция, архив, дублирование, удаление вклада.

- Вклад создаёт расход (или движение) с `goal_id` и обновляет `current_amount`.
- Вклад в archived/completed цель — блокируется.
- Бюджеты **не** учитывают взносы в цели как обычный расход категории (см. budgets).

---

## Долги — `debts.py`

Создание/правка, погашение с выбранного счёта, начисление процентов, проекция, просрочка, undo платежа, справочник контрагентов.

Погашение пишет транзакцию с `debt_id` и уменьшает остаток долга (с FX при необходимости).

---

## Подписки — `subscriptions.py`

| Операция | Смысл |
|----------|--------|
| Create/Update/Delete | Карточка подписки |
| Pause / Resume | Статус |
| `ChargeSubscriptionNow` | Ручное списание |
| `ProcessDueSubscriptions` | Фоновый проход due + auto_charge |
| Analytics | Сводка для UI |

При `check_balance_before_subscription` и нехватке средств — код/`insufficient_funds` → локализованное сообщение.

---

## Бюджеты — `budgets.py`

| Операция | Смысл |
|----------|--------|
| Set / Delete | Лимит категории на месяц |
| Progress / List month | UI прогресса |
| Recalculate | Пересчёт из транзакций |
| `apply_expense_delta` | Инкремент при add/update/delete expense |

Категория бюджета — expense или both; нужен положительный лимит.

---

## Категории — `categories.py`

List / Create / Update / Delete / FindOrCreate — для пикера и форм.

`UpdateCategoryUseCase` при смене имени (и при любом сохранении) переименовывает **все** операции той же категории в том же скоупе счёта (личные vs корпоративные), включая позиции чека. Иначе плитки без точного совпадения имени показывают стрелки дохода/расхода вместо иконки.

---

## Валюты — `currencies.py`

| Класс | Назначение |
|-------|------------|
| `UpdateExchangeRatesUseCase` | Тянет фиат + крипто курсы в БД |
| `ConvertCurrencyUseCase` | Разовая конвертация |
| `ListCurrenciesUseCase` | Каталог |

---

## Настройки — `settings.py`

`GetSettingsUseCase` / `UpdateSettingsUseCase` — тема, язык, базовая валюта, интервал курсов, уведомления, график дашборда и т.д.

PIN:

| Use case | Роль |
|----------|------|
| `GetPinCredentialsUseCase` | Прочитать hash/salt/biometric flag |
| `SetPinCredentialsUseCase` | Сохранить PIN (+ biometric) |
| `ClearPinCredentialsUseCase` | Сбросить PIN и biometric |

UI не пишет PIN напрямую в репозиторий.
---

## Экспорт — `export_data.py`

`ExportDataUseCase` — JSON-снимок домена в `exports/`.  
Опционально AES-обёртка паролем пользователя (encrypt/decrypt blob).

---

## Выравнивание валют — `align_currencies.py`

`align_sole_account_currency(container)` — если один счёт и его валюта расходится с базовой в настройках, пытается привести к базе (при наличии курса). Вызывается при старте из `_seed_if_needed`.

---

## Ошибки домена → UI

Английские `ValueError(...)` / `ExchangeSyncError(...)` в presentation превращаются в ключи i18n через `user_facing_error` / `snack_exception` (`_DOMAIN_ERROR_KEYS` + prefixes).

- Известные тексты → понятные ru/en/uz.
- Неизвестный technical English / traceback-подобные строки → `error.generic`.
- Пользователь не видит сырой exception / SQL / пути.
---

## Связанные документы

- Модели — [ENTITIES.md](ENTITIES.md)  
- Реализации — [INFRASTRUCTURE.md](INFRASTRUCTURE.md)  
- UI-вызовы — [PRESENTATION.md](PRESENTATION.md)  
