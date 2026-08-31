# Производительность FinWise

Цель: быстрый отклик UI на Android / iOS и Windows **без урезания функций**.

---

## 1. Слои оптимизации

| Слой | Что ускоряем |
|------|----------------|
| SQLite | WAL + составные индексы; границы `date_from` / `date_to`; батч UPDATE |
| Domain | Один scan месяца для всех бюджетов; TTL RateBook; без N× `list_rates` |
| Presentation | Без многокадровой анимации графика на каждый reload; один `list_pending` для бейджей; count-up только по marked money-текстам |

Индексы и границы периода — [DATABASE.md](DATABASE.md).

---

## 2. Кэш RateBook

- Модуль: `lib/domain/services/rate_cache.py`
- TTL ≈ **90 с**; ключ связан с экземпляром currency repository
- **Инвалидация:** после `update_exchange_rates`, restore / wipe, явный `invalidate_rate_book_cache()`
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
| Home cashflow | Всегда с верхней границей даты (`date_to`) |

Лента операций: фильтры + пагинация; теги фильтруются в Python до LIMIT.

---

## 4. Уведомления (бейджи)

`pending_counts(...)` — **один** проход `list_pending`, затем фильтры по группам (цели / долги / подписки / бюджеты). Не N отдельных запросов на каждый вид бейджа.

---

## 5. Бюджеты

`RecalculateBudgetSpentUseCase`:

1. Один `transactions.list(EXPENSE, month)`  
2. Агрегация `category → spent` (с RateBook)  
3. Save всех бюджетов месяца  

Инкрементальные дельты при add/update/delete expense — `apply_expense_delta` (без полного пересчёта, где возможно).

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

- Не грузить unbounded историю (`all` = 5 лет).
- Индексы создаются при `init_db` на любом устройстве.
- Нативные сервисы только через `page.services`, не `page.add`.
- Web-preview (`flet run --android`) без Dart-плагинов — ожидаемо быстрее по плагинам, но это не «настоящий» APK.

---

## 8. Анимации UI (не БД)

**Count-up** денег при Refresh (`count_up.py`, ~0.55 с) — визуальный эффект; не умножает SQL. Скрытый баланс и простые % KPI пропускаются.

---

## 9. Тесты

`tests/unit/test_performance.py` покрывает:

- tags-before-limit  
- rate cache  
- pending_counts  
- budget recalc batch  
- clear_goal_links  
- analytics `all` bound  

Полный прогон: `python -m pytest -q`.

---

## 10. Известные улучшения (не блокер релиза)

См. `.cursor/agent/AUDIT.md` (локальные заметки агента): lazy pager аналитики, in-place mutate на dashboard, off-screen reload, ListView storms, batch ConvertCurrency, дефолтное окно списка операций, SQL search.

Эти пункты не отменяют уже внедрённые индексы и батчи.

---

## Связанные документы

- [DATABASE.md](DATABASE.md)  
- [PRESENTATION.md](PRESENTATION.md)  
- [TESTING.md](TESTING.md)  
