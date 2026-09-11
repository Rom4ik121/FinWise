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
| `ListTransactionsUseCase` | Фильтры: счёт, даты, тип, теги, transfer, **`has_debt`**, **`amount_min`/`amount_max`**, FTS `query` (категория/комментарий/теги/payee/сумма), limit/offset |
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
| `CreateAccountUseCase` | Новый счёт. Первый счёт задаёт `settings.default_currency` и `currency_user_set`. |
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
| `ProcessDueSubscriptions` | Фоновый проход due + auto_charge. Нет счёта (dangling id) → `PAUSED` + `auto_charge=False`. |
| Analytics | Сводка для UI |

При `check_balance_before_subscription` и нехватке средств — код/`insufficient_funds` → локализованное сообщение.

`preview_occurrence_dates` — следующие даты серии (форма создания/правки). Skip / pause / catch-up при старте приложения (`process_due_subscriptions`, до 31 списания).

---

## Повторяющиеся шаблоны — `recurring.py`

Отдельная сущность от подписок (доход не должен портить аналитику стоимости подписок).

| Класс | Назначение |
|-------|------------|
| Create / Update / Delete / List | Шаблоны income/expense. **Create** сдвигает `next_run` на следующий период, если дата ≤ сегодня — сохранение не проводит операцию сразу. Catch-up работает для уже существующих правил. |
| `PauseRecurringRuleUseCase` | Пауза без удаления |
| `SkipRecurringOccurrenceUseCase` | Пропустить ближайшую дату |
| `ProcessDueRecurringRulesUseCase` | Автосоздание в ledger + catch-up (старт приложения, до 31). Нет счёта → `paused` + `auto_create=False`. |

Интервалы: daily / weekly / monthly / yearly, `interval_count`. Тег созданных операций: `recurring`.

---

## Импорт CSV — `import_csv.py`

| Класс | Назначение |
|-------|------------|
| `PreviewCsvImportUseCase` | Кодировка, разделитель, пресеты колонок, dry-run строк |
`CommitCsvImportUseCase` — создание операций через `AddTransactionUseCase` (тег `csv-import`) в одном `unit_of_work`: ошибка на середине батча откатывает уже записанные строки.

Парсер: `lib/domain/services/csv_statement.py`.

---

## Капитал — `net_worth.py`

| Класс | Назначение |
|-------|------------|
| `RecordNetWorthSnapshotUseCase` | Upsert снимка include-in-total за UTC-день (FX через `sum_balances_in_base`). Нет курса → снимок **не** пишется (частичная сумма не попадает в историю). |
| `ListNetWorthSnapshotsUseCase` | Окно для графика аналитики |

Снимок пишется после commit операции и при старте приложения.

---

## Бюджеты — `budgets.py`

| Операция | Смысл |
|----------|--------|
| Set / Delete | Лимит категории на месяц |
| Progress / List month | UI прогресса |
| Recalculate | Пересчёт из транзакций |
| `apply_expense_delta` | Инкремент при add/update/delete expense |

Категория бюджета — expense или both; нужен положительный лимит.

Пороги уведомлений (`budget_warn_pct` / `budget_limit_pct`, по умолчанию 80 / 100) задаются в настройках. Пересечение порога → in-app + локальное уведомление; повтор той же ступени не шлётся (`last_alert_level`). Смена лимита сбрасывает watermark, чтобы новый порог мог сработать снова.

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

`GetSettingsUseCase` / `UpdateSettingsUseCase` — тема, язык, базовая валюта, интервал курсов, уведомления, график дашборда, пороги бюджета, JSON фильтров операций и т.д.

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

- Известные тексты → понятные строки на языке UI (18 LTR локалей).
- Неизвестный technical English / traceback-подобные строки → `error.generic`.
- Пользователь не видит сырой exception / SQL / пути.
---

## Связанные документы

- Модели — [ENTITIES.md](ENTITIES.md)  
- Реализации — [INFRASTRUCTURE.md](INFRASTRUCTURE.md)  
- UI-вызовы — [PRESENTATION.md](PRESENTATION.md)  
