# Use cases

Все сценарии — async-классы с `execute()`. Собираются в `Container`.

## Транзакции (`transactions.py`)

| Use case | Поведение |
|---|---|
| `AddTransactionUseCase` | Пишет операцию, двигает баланс счёта, при `goal_id` / `debt_id` двигает цель/долг, пересчитывает бюджет |
| `UpdateTransactionUseCase` | Пересчёт баланса; сумму ноги перевода менять нельзя |
| `DeleteTransactionUseCase` | Реверс баланса/цели/долга/бюджета; перевод удаляется парой |
| `ListTransactionsUseCase` | Фильтры: счёт, категория, тип, даты, теги, goal/debt/subscription/transfer |
| `GetTransactionStatsUseCase` | Доход/расход по периодам и категориям; **переводы исключены** |
| `TransferAccountsUseCase` | Пара expense+income с общим `transfer_id`; FX через RateBook |

Баланс счёта: `initial_balance + Σ income − Σ expense` (включая ноги перевода).
В статистике и бюджетах переводы не участвуют.

## Счета (`accounts.py`)

CRUD. Удаление каскадно снимает транзакции и подписки счёта (FK `ON DELETE CASCADE`).
`RecalculateAccountBalanceUseCase` пересобирает баланс из журнала.

## Цели (`goals.py`)

CRUD, архив, дубль (`current_amount=0`).  
`ContributeToGoalUseCase` создаёт **расход** со счёта (`type=expense`, `goal_id`,
`goal_credit_amount` в валюте цели).  
Проекция: ежемесячный взнос, дата завершения, `is_on_track`.

## Долги (`debts.py`)

CRUD, архив. Погашение — расход с `debt_id` и `debt_credit_amount`.
Проценты: `principal × rate × days / 365 / 100`.  
`MarkOverdueDebtsUseCase` — `due_date < now`.

## Подписки (`subscriptions.py`)

`ProcessDueSubscriptionsUseCase` на старте и в фоне: расход, сдвиг
`next_billing_date`, учёт `payments_made` / `max_payments` / `end_date`.
Опция `check_balance_before_subscription`. Пауза/ручной платёж/аналитика.

## Валюты (`currencies.py`)

Обновление курсов (fiat+crypto), конвертация (прямая → обратная → USD), список.

## Бюджеты (`budgets.py`)

Лимит на категорию/месяц (только expense/both). `spent` из расходов без
`transfer_id`. Алерты 80% и 100%, если `budget_alerts`.

## Категории (`categories.py`)

CRUD, `FindOrCreateCategoryUseCase` (уникальное имя). Переименование тянет бюджеты.

## Настройки и экспорт

`GetSettingsUseCase` / `UpdateSettingsUseCase`.  
`ExportDataUseCase` — JSON snapshot (счета, операции, цели, долги, подписки,
валюты, курсы, настройки). JSON **не** подставляется как restore БД — для
полного отката нужен файл `.db` бэкапа.

`align_sole_account_currency` — если один счёт и его валюта ≠ базовой,
меняет код валюты счёта и его операций без FX.

## Голос (`voice_capture.save_spoken_transaction`)

Разбор фразы → find_or_create категории → `AddTransactionUseCase` на первый
активный счёт. Нужны сумма > 0 и имя категории (не пустое «Прочее»).
