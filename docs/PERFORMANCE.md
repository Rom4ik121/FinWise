# Производительность FinWise

Цель: быстрый отклик UI на Android / iOS и Windows **без урезания функций**, в том числе при тысячах операций в ledger.

---

## 1. Слои оптимизации

| Слой | Что ускоряем |
|------|----------------|
| SQLite | WAL + составные индексы; границы `date_from` / `date_to`; батч UPDATE |
| Domain | Один scan месяца для всех бюджетов; TTL RateBook; paging ledger; без N× `list_rates` |
| Presentation | Без многокадровой анимации графика на пассивный reload; явный refresh — count-up + chart queue; один `list_pending` для бейджей; `reload_gate` coalesce + skip hidden tabs; overlay reuse (`push_overlay`); шрифты/кольца/donut от ширины карточки (`fit_font`) |

Индексы и границы периода — [DATABASE.md](DATABASE.md).

---

## 2. Кэш RateBook

- Модуль: `lib/domain/services/rate_cache.py`
- TTL ≈ **90 с**; ключ связан с экземпляром currency repository
- **Инвалидация:** после `update_exchange_rates` / upsert rates, restore / wipe, явный `invalidate_rate_book_cache()`
- **UI:** `load_rate_book` / `safe_convert` в `presentation/utils.py`
- **Domain:** бюджеты, stats, transfer FX, goal / debt credit

Нет курса → явная ошибка пользователю (не тихий fallback).

---

## 3. Графики и списки

| Место | Поведение |
|-------|-----------|
| Home compact chart | `animate=False` → мгновенная отрисовка; downsample ≤ ~40 точек |
| Analytics / account detail reload | `animate=False` (без десятков `safe_update` кадров) |
| Analytics период `all` | ≤ 36 месяцев в окне 5 лет |
| Home cashflow | Верхняя граница даты + **paged** load |

### Пагинация ledger

Тяжёлые выборки **не** делают unbounded `list()`:

| Модуль | Роль |
|--------|------|
| `lib/domain/transaction_paging.py` | `list_transactions_paged` / `fold_transaction_pages` |
| `lib/presentation/tx_query.py` | Обёртка над use case `execute` |

Параметры по умолчанию: **`page_size=500`**, **`max_rows=25_000`**.

Используется на: cashflow dashboard, analytics, account detail, sparkline debts/subs/budgets lookback, export JSON/CSV/PDF paths, currency migrate/align, month budget scan, `GetTransactionStatsUseCase`.

Запись PDF (reportlab + matplotlib Agg) уходит в `asyncio.to_thread`, чтобы форма экспорта не зависала на телефоне.

Фильтр репозитория **`has_debt`** — sparklines долгов не сканируют весь ledger.

Лента операций (UI): день/диапазон + пагинация страницы; теги фильтруются в Python **до** LIMIT; поиск ограничен scan limit.

---

## 4. Уведомления (бейджи)

`pending_counts(...)` — **один** проход `list_pending`, затем фильтры по группам (цели / долги / подписки / бюджеты). Не N отдельных запросов на каждый вид бейджа.

---

## 5. Бюджеты

`RecalculateBudgetSpentUseCase`:

1. Один paged `transactions.list(EXPENSE, month)`  
2. Агрегация `category → spent` (с RateBook)  
3. Save всех бюджетов месяца  

**Когда полный пересчёт:**

| Экран | Поведение |
|-------|-----------|
| Budgets page | При открытии / reload |
| Dashboard / Analytics | Только explicit refresh (`animate=True`) |
| Add/update/delete expense | Инкремент `apply_expense_delta` (без полного scan) |

---

## 6. Старт приложения

Порядок в `lib/main.py` рассчитан на телефоны:

1. Лёгкий splash (без тяжёлых сервисов в дереве виджетов).
2. DB + DI + seed.
3. UI (`FinanseApp.start`).
4. **После первого кадра:** due-subscriptions, push permission, schedule reminders, daily backup.

Тяжёлые циклы (курсы, reminders, hourly daily-backup check) — фоновые `page.run_task`, не блокируют первый paint.

---

## 7. Мобильные платформы

Тот же Python/SQLite/UI. Критично:

- Не грузить unbounded историю (`all` = 5 лет; ledger pages capped).
- Индексы создаются при `init_db` на любом устройстве.
- Нативные сервисы только через `page.services`, не `page.add`.
- Web-preview (`flet run --android`) без Dart-плагинов — ожидаемо быстрее по плагинам, но это не «настоящий» APK.

---

## 8. Анимации и UI-хелперы (не БД)

| Модуль | Роль |
|--------|------|
| `count_up.py` | Count-up денег при Refresh (~0.55 с); скрытый баланс / простые % KPI пропускаются |
| `ui_motion.py` | `replace_controls`, scroll memory, animate flag, `wrap_enter` / `chart_enter`, overlay fade |
| `reload_gate.py` | Слияние `reload()`; скрытые вкладки **не** перезагружаются, пока снова на экране |
| `fullscreen_form.py` | `push_overlay` / dismiss: один слот на ключ, дерево формы сбрасывается (без утечки overlay на телефоне) |
| `widgets/period_scale.py` | Шкала периода на summary rings |
| `layout.make_v_scroll` | Общий ListView + scroll memory (Goals/Debts/…) |

---

## 9. Тесты

`tests/unit/test_performance.py` покрывает:

- tags-before-limit  
- rate cache  
- pending_counts  
- budget recalc batch  
- clear_goal_links  
- analytics `all` bound  
- paged fetch + `has_debt`  

Дополнительно: `test_reload_gate.py`, `test_period_scale.py`.

Полный прогон: `python -m pytest -q`.

---

## 10. Известные улучшения (не блокер релиза)

Закрыто (2026-09-04):

- full budget recalc только на explicit refresh (home/analytics); Budgets page — при открытии;
- paged `list_transactions` (`tx_query` / `transaction_paging`, page=500, cap=25k);
- `has_debt` filter для sparkline debts.

Остаётся backlog: _(пусто — slice 2026-09-04 закрыт)_.

Закрыто дополнительно (2026-09-04 evening):

- dashboard / debts KPI → `ledger_fx` (единый FX path);
- `ConvertCurrencyUseCase` через RateBook cache + `execute_many`;
- ReloadGate: off-screen не drain'ит после первого paint (явный visible flag; `control.page` на кэшированных вкладках всё ещё set);
- overlay: `push_overlay` reuse слота + `dismiss_fullscreen` обнуляет дерево без `page.update()`;
- transaction filter range capped at 365 days.

Закрыто (2026-09-04 night):

- Dashboard in-place mutate (balance/chart/sections slots; soft reload);
- ListView storms: goals/debts/subs entity cache + no spinner on search filter;
- SQL FTS5 `transactions_fts` (Alembic **0022**/**0028** + `database.py` ensure: category/comment/tags/payee/amount); UI `query=`.

---

## Связанные документы

- [DATABASE.md](DATABASE.md)  
- [PRESENTATION.md](PRESENTATION.md)  
- [TESTING.md](TESTING.md)  
