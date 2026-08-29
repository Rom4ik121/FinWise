# Инфраструктура

## Репозитории

Все `SqlAlchemy*Repository` реализуют порты domain и ходят в SQLite через
`asyncio.to_thread` + `session_scope`.

| Класс | Таблица | Заметки |
|---|---|---|
| Account | accounts | CRUD, `active_only` |
| Transaction | transactions | Фильтры; теги дофильтровываются в Python |
| Goal | goals | status/currency/priority, сортировки |
| Debt | debts | status/direction, сортировки |
| Subscription | subscriptions | `list_due(as_of)` |
| Currency | currencies, exchange_rates | upsert, `seed_from_json` |
| Category | categories | `find_or_create`, имя без учёта регистра |
| Settings | settings | get/update, PIN |
| Budget | budgets | spent, delete/reassign категории |

## HTTP

| Клиент | Источник |
|---|---|
| `ExchangeRateClient` | open.er-api.com, fiat от base |
| `CryptoRateClient` | CoinGecko |
| `BinanceRateClient` | Binance ticker, USDT≈USD |

Таймауты, свой `httpx.AsyncClient` для тестов, `aclose()`.

## Сервисы

**BackupService** — копия `.db` + `-wal`/`-shm`, restore с safety-копией,
`list_backups` / `delete_backup`.

**ExportService** — CSV операций, PDF-сводка (счета, операции, цели, долги, подписки).

**EncryptionService** — PBKDF2 PIN; делегирует биометрию в `biometric.py`.

**biometric.py** — Windows Hello (winrt) или `FinanseLocalAuth`. Регистрация
только через `attach_page_service` (`flet_services.py`). Никогда `page.add(service)`.

**flet_services.attach_page_service** — `page.services`. Кастомные расширения
пропускаются, если `page.web` (preview с ПК). FilePicker/Share: `native_extension=False`.

**NotificationService** — очередь; `push` зовёт `dispatch_push`.

**push_notifier.py** — `FinanseLocalNotifications` (iOS+Android, show/schedule),
опциональный import `FletAndroidNotifications` (не в requirements: ломает
IPA из‑за `timezone`), Windows toast. `reminder_fire_at` — UTC-момент для
OS schedule. Env `FINANCE_DISABLE_PUSH`.

**reminder_scheduler.py** — in-app долги/подписки/цели + OS schedule на 30 дней.

**speech.py / voice_parse.py / voice_capture.py** — listen → разбор фразы →
транзакция.

**localization.py** — ключи ru/en/uz, каждая запись обязана иметь все три языка
(тест `test_every_key_has_all_langs`).

**data_reset_service.py** — wipe таблиц с учётом FK.

**HttpExchangeRateProvider** — склейка fiat+crypto в пары и запись в БД.

## Flutter-расширения (`extensions/`)

Ставятся `-e` из `requirements.txt`. В IPA/APK попадают только после
`flet build`.

| Пакет | Control | Роль |
|---|---|---|
| flet_local_auth | FinanseLocalAuth | Face ID / отпечаток |
| flet_local_notifications | FinanseLocalNotifications | show + zonedSchedule |
| flet_speech | FinanseSpeech | STT, событие `voice_request`, `take_pending_voice` |

На web-клиенте эти типы неизвестны — их нельзя класть в дерево виджетов.
