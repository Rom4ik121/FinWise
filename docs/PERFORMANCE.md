# Производительность FinWise

Цель: мгновенный отклик UI на телефонах (Android/iOS) и десктопе **без урезания функций**.

## Слои

| Слой | Что ускоряем |
|------|----------------|
| SQLite | WAL + составные индексы; границы `date_from`/`date_to`; батч UPDATE |
| Domain | один scan месяца для всех бюджетов; TTL RateBook; без N× `list_rates` |
| Presentation | без 40-кадровой анимации графика на каждый reload; один `list_pending` для бейджей |

## RateBook cache

- Модуль: `lib/domain/services/rate_cache.py` (реэкспорт `lib/core/rate_cache.py`)
- TTL ≈ 90 с; ключ = `id(currency_repository)`
- Инвалидация: после `update_exchange_rates`, restore/wipe, явный `invalidate_rate_book_cache()`
- UI: `load_rate_book` / `safe_convert` в `presentation/utils.py`
- Domain: бюджеты, stats, transfer FX, goal credit

## Графики

- Home compact: `animate=False` → мгновенная отрисовка
- Analytics / account detail reload: `animate=False` (без десятка `safe_update` кадров)
- Плотная серия: downsample ≤40 точек на home; analytics `all` ≤36 месяцев

## Уведомления

`pending_counts(...)` — один проход `list_pending`, затем фильтры по kind-группам (цели/долги/подписки/бюджеты).

## Бюджеты

`RecalculateBudgetSpentUseCase`: один `transactions.list(EXPENSE, month)` → `dict[category → spent]` → save всех бюджетов месяца.

## Мобильные платформы

Те же SQLite-пути и код UI (Flet). Критично не грузить всю историю:

- период `all` = 5 лет (не unbounded)
- home cashflow всегда с `date_to`
- индексы создаются при `init_db` на любом устройстве

## Тесты

`tests/unit/test_performance.py` — tags-before-limit, rate cache, pending_counts, budget recalc, clear_goal_links, analytics `all` bound.

Полный прогон: `pytest tests/`.

## Оставшиеся (AUDIT, не блокируют)

| # | Тема |
|---|------|
| 53 | Analytics lazy pager sections |
| 54 | Dashboard in-place text mutate vs full rebuild |
| 57–60 | Off-screen reload, ListView, update storms |
| 67–70 | ConvertCurrency batching, default 90d tx list, SQL search |
