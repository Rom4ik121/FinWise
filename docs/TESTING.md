# Тестирование

## 1. Как запускать

Из корня репозитория:

```powershell
python -m pytest -q
python -m pytest tests/unit -q
python -m pytest tests/integration -q
```

Точечно:

```powershell
python -m pytest tests/unit/test_performance.py tests/integration/test_transfers.py -q
```

### Конфиг

`pytest.ini`:

- `testpaths = tests`
- `pythonpath = .`

Async в тестах — через `asyncio.run` / `tests.conftest.run_async` (**без** обязательного pytest-asyncio).

---

## 2. Фикстуры (`tests/conftest.py`)

| Фикстура / поведение | Смысл |
|----------------------|--------|
| Autouse `FINANCE_DISABLE_PUSH=1` | Не слать OS-toast в CI |
| `container(tmp_path)` | Отдельный SQLite на тест + собранный DI |
| `tests/factories.py` | Account, Transaction, Goal, Debt, Subscription, Category |

Биометрия в unit-тестах: `FINANCE_BIOMETRIC_OK=1` и/или `set_local_auth_service`.

---

## 3. Юнит-тесты (`tests/unit/`)

Покрывают чистые функции и изолированные сервисы, в том числе:

| Область | Примеры файлов |
|---------|----------------|
| Деньги / ввод | `test_money.py`, `test_money_input.py` (filter bounds: blank ≠ 0) |
| Alembic | `test_alembic_chain.py` (single head **0029**, `upgrade head` on empty SQLite, legacy `0002_reminder_time` rewrite) |
| Бюджеты (логика) | `test_budget.py` |
| Биометрия / PIN | `test_biometric.py`, `test_encryption.py`, `test_secret_box.py` |
| Локализация | `test_localization.py` (все ключи всех `SUPPORTED_LANGS`), `test_locale_prefs.py`, `test_first_run_language.py` |
| Бэкап | `test_backup_service.py` (daily rolling, SQLite snapshot, `.fwbackup`, embedded key) |
| Secret box / Keychain | `test_secret_box.py` |
| Курсы / RateBook | `test_rate_book.py`, currency helpers |
| Проекции | `test_goal_projection.py`, `test_debt_projection.py` |
| Подписки (биллинг) | `test_subscription_billing.py` |
| Reminders / push | `test_reminder_scheduler.py`, `test_notification_service.py`, `test_push_notifier.py` |
| AppState / скины | `test_app_state.py`, `test_skins.py` |
| Иконки / каталог | `test_account_icons.py`, `test_icon_catalog.py`, `test_exchanges.py` (в т.ч. auth → user_facing) |
| Аналитика периодов | `test_analytics_period.py` |
| UI helpers | `test_reload_gate.py`, `test_period_scale.py` |
| Performance | `test_performance.py` (tags, RateBook, paging, `has_debt`, budget batch) |
| UI smoke / utils | `test_ui_widgets_smoke.py`, `test_presentation_utils.py`, `test_charts.py` |
| Файлы / Flet services | `test_file_transfer.py`, `test_flet_services.py` |
| Push | `test_push_notifier.py`, `test_notification_service.py` |
| Пути iOS/Android | `test_config_ios.py` |
| iOS IPA patch | `test_ios_notifications.py` (AppDelegate, Info.plist, PrivacyInfo) |
| PIN / lock | `test_encryption.py`, `test_app_state.py` (`reload_pin_gate`) |
| Медиа / бэкап | `test_media_store.py` (path confinement), `test_backup_service.py` (embedded key, fwbackup) |
| Формы | `test_form_validation.py`, `test_money_input.py` (live grouping + caret-prepend `50` + write-echo `500`) |
| UX helpers | `test_count_up.py`, `test_frequent_account.py`, `test_form_keyboard.py`, `test_ui_motion.py`, `test_tx_filters_panel.py`, `test_responsive.py` (375px nav) |

---

## 4. Интеграция (`tests/integration/`)

Сценарии с реальной SQLite через фикстуру `container`:

| Область | Файл |
|---------|------|
| Счета | `test_accounts.py` |
| Операции / позиции чека | `test_transactions.py`, `test_transaction_items.py` |
| Переводы + FX | `test_transfers.py` (fee on destination deleted with the pair) |
| Цели / долги / подписки | `test_goals.py`, `test_debts.py` (interest tag stamp + reverse), `test_subscriptions.py` |
| Бюджеты | `test_budgets.py` (debt repayments skipped; category match is case-insensitive), `test_budget_items_parity.py` |
| Категории / валюты | `test_categories.py`, `test_currencies.py` |
| Курсы upsert / safe convert | `test_exchange_rate_upsert.py`, `test_safe_convert.py` |
| Биржевой синк | `test_exchange_sync.py` |
| Настройки / экспорт / align | `test_settings_export_align.py` |

Также есть корневые smoke-тесты вроде `tests/test_money_and_transactions.py`.

---

## 5. Правила написания тестов

1. Сценарии с БД и side-effects ledger → **integration** + `container`.
2. Чистые функции и парсеры → **unit**.
3. Не включать реальные OS-toast / биометрию устройства в CI.
4. После изменений domain / money / FX / transfers — прогнать хотя бы  
   `tests/integration/test_transfers.py` и релевантный unit.
5. Новые ключи i18n — убедиться, что `test_localization` проходит (все живые UI-языки).
6. Не фиксировать в документации «N passed» — число растёт; ориентир — зелёный `pytest -q`.

---

## 6. Связанные документы

- Инварианты — [ARCHITECTURE.md](ARCHITECTURE.md), [USE_CASES.md](USE_CASES.md)  
- Perf-кейсы — [PERFORMANCE.md](PERFORMANCE.md)  
