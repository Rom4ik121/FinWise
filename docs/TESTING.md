# Тестирование

```powershell
python -m pytest -q
python -m pytest tests/unit -q
python -m pytest tests/integration -q
```

`pytest.ini`: `testpaths = tests`, `pythonpath = .`. Async в тестах —
`asyncio.run` / `tests.conftest.run_async`, без pytest-asyncio.

## Фикстуры

- autouse `FINANCE_DISABLE_PUSH=1`
- `container(tmp_path)` — отдельный SQLite на тест
- `tests/factories.py` — Account, Transaction, Goal, Debt, Subscription, Category

## Юнит (`tests/unit/`)

Деньги и ввод, бюджет, биометрия (в т.ч. «сервис не в page.add», пропуск web),
шифрование PIN, локализация (все ключи ru/en/uz), бэкап файлов, валюты,
проекции целей/долгов, биллинг подписок, reminder scheduler, notification
queue, push (`reminder_fire_at`), RateBook, AppState, иконки, аналитика периодов, **performance** (tags paging,
rate cache, budget batch, pending_counts, goal unlink), скины, smoke виджетов,
 **file_transfer** (безопасное имя, sqlite
magic, копия в выбранный путь), **flet_services** (web skip / builtin),
**voice_parse** / **voice_capture**, пути iOS/Android.

## Интеграция (`tests/integration/`)

Счета, операции, переводы (FX, удаление пары, исключение из статистики),
цели, долги, подписки, бюджеты, категории, курсы, upsert, safe convert,
настройки и JSON-экспорт.

На прогоне репозитория: **262 passed, 2 skipped**.

## Правила

- Сценарии с БД — integration + фикстура `container`.
- Чистые функции — unit.
- Биометрия: `FINANCE_BIOMETRIC_OK=1` или `set_local_auth_service`.
- Не включать реальные OS-toast в CI.
