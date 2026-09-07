# Инфраструктура

Реализации портов domain, HTTP-клиенты, OS-сервисы и Flutter-расширения.  
Код: `lib/infrastructure/`. Domain **не** импортирует этот слой.

---

## 1. ORM и репозитории

### `db_models.py`

SQLAlchemy 2.0 declarative-модели таблиц (см. [DATABASE.md](DATABASE.md)).

### Паттерн доступа

Все `SqlAlchemy*Repository`:

1. Реализуют ABC из `lib/domain/repositories/`.
2. Выполняют синхронный SQLAlchemy в **`asyncio.to_thread`** + `session_scope` (вне UoW).
3. Внутри `unit_of_work` — тот же поток, без лишнего `to_thread` на nested calls (`in_unit_of_work`).
4. Маппят ORM ↔ Pydantic-сущности.

| Класс | Таблица / таблицы | Заметки |
|-------|------------------|---------|
| `SqlAlchemyAccountRepository` | `accounts` | CRUD, `active_only`, `corporate`, `include_in_total` |
| `SqlAlchemyTransactionRepository` | `transactions` | Фильтры по счёту/дате/типу/связям/`has_debt`; **теги** дофильтровываются в Python **до** LIMIT/OFFSET |
| `SqlAlchemyGoalRepository` | `goals` | status / priority / сортировки |
| `SqlAlchemyDebtRepository` | `debts` | status / direction |
| `SqlAlchemySubscriptionRepository` | `subscriptions` | `list_due(as_of)` |
| `SqlAlchemyCurrencyRepository` | `currencies`, `exchange_rates` | upsert, `seed_from_json` |
| `SqlAlchemyCategoryRepository` | `categories` | `find_or_create`, имя без учёта регистра |
| `SqlAlchemySettingsRepository` | `settings` | get/update; PIN hash/salt; biometric flag |
| `SqlAlchemyBudgetRepository` | `budgets` | spent, delete/reassign категории |
| `SqlAlchemyExchangeConnectionRepository` | `exchange_connections` | credentials blob, holdings, last_error |

Базовый хелпер сессий: `lib/infrastructure/repositories/_base.py` (re-export UoW из `lib/domain/unit_of_work.py`).

---

## 2. HTTP и курсы

| Клиент | Файл | Источник |
|--------|------|----------|
| `ExchangeRateClient` | `api/exchange_rate_client.py` | open.er-api.com — фиат от base |
| `CryptoRateClient` | `api/crypto_rate_client.py` | CoinGecko |
| `BinanceRateClient` | `api/binance_rate_client.py` | Binance ticker; USDT ≈ USD |
| `CcxtExchangeClient` | `api/ccxt_exchange_client.py` | Балансы / сделки через CCXT; в APK/IPA — mobile-safe wheel `vendor/wheels/` (без aiodns/pycares). Auth fail → `Invalid exchange API credentials` (quiet warning, без traceback spam) |

Общие свойства: таймауты, опциональный свой `httpx.AsyncClient` (удобно в тестах), `aclose()`.

**`HttpExchangeRateProvider`** (`services/exchange_rate_provider.py`) склеивает fiat + crypto в пары и пишет в БД через репозиторий валют. Use case: `UpdateExchangeRatesUseCase`.

Кэш доменного `RateBook`: `lib/domain/services/rate_cache.py` (TTL ≈ 90 с). После обновления курсов — `invalidate_rate_book_cache()`.

---

## 3. Безопасность и секреты

### PIN и шифрование

- **`EncryptionService`** — PBKDF2 для PIN (hash + salt в `settings`).
- Биометрия делегируется в `biometric.py`.

### Face ID (`biometric.py`)

- Мобильный путь: `FinanseLocalAuth` (расширение `flet_local_auth`).
- **Политика продукта:** разблокировка только **face / iris**. Отпечаток пальца и Windows Hello fingerprint **не** предлагаются.
- Desktop без face-моста → только PIN.
- Env для тестов: `FINANCE_BIOMETRIC_OK=1`.

### Ключи бирж

- **`secret_box.py`** — AES-GCM; ключ в файле `.secret_box_key` в каталоге данных.
- В БД хранится только `credentials_encrypted`.

### Ошибки UI

Не инфраструктура напрямую, но контракт: логировать полный exception; пользователю — `user_facing_error` / `snack_exception` в presentation.

---

## 4. Бэкап и экспорт

### `BackupService`

| Метод | Поведение |
|-------|-----------|
| Ручной backup | Timestamped копия `.db` (+ `-wal` / `-shm` при наличии) в `backups/` |
| `ensure_daily_backup()` | Перезаписывает **`finanse_daily.db`** не чаще **одного раза в локальные сутки** (+ штамп `finanse_daily.day`) |
| Restore | Проверка заголовка SQLite (`b"SQLite format 3\0"`); иначе ошибка; safety-копия текущего файла |
| list / delete | Управление файлами бэкапов |

Вызов daily: старт приложения + hourly loop в `lib/main.py`.

### `ExportService`

- CSV операций.
- PDF-сводка и отчёт по счёту — reportlab / matplotlib; кириллица через `assets/fonts/LiberationSans*.ttf` (не Helvetica).
- Настраиваемый экспорт: период (в т.ч. свои даты), scope счетов (все / личные / корпоративные / выбранные), разделы (`PdfSectionFlags`).

### `ExportDataUseCase` + шифрование JSON

JSON-снимок домена в `exports/`; опциональная AES-обёртка паролем пользователя.

### `DataResetService`

Wipe таблиц с учётом FK — «сброс данных» в настройках.

---

## 5. Уведомления и напоминания

| Модуль | Роль |
|--------|------|
| `notification_service.py` | Очередь in-app уведомлений; `push` → `dispatch_push` |
| `push_notifier.py` | Mobile (`FinanseLocalNotifications` + launcher icon), Windows toast, Linux `notify-send` with `assets/icon.png`; **не** тянуть `flet-android-notifications` в IPA. iOS: `DarwinInitializationSettings` + `requestPermissions` при init и в `_post_start`, иначе нет пункта в Настройки → Уведомления |
| `reminder_scheduler.py` | In-app долги/подписки/цели + OS schedule ~30 дней вперёд |

Env: **`FINANCE_DISABLE_PUSH=1`** — отключить OS-push (в pytest включено autouse).

Haptic на успех snack: лёгкая вибрация через notifications plugin на мобильных (`haptics.py`); на desktop — no-op.

---

## 6. Flet-сервисы (`flet_services.py`)

**Критично:** кастомные Service **нельзя** класть в `page.add()` — на splash будет `Unknown control`.

Правильный путь: `attach_page_service` → `page.services`.

- На **`page.web is True`** (preview / `flet run --android`) нативные расширения **пропускаются**.
- FilePicker / Share: `native_extension=False` где уместно.

---

## 7. Локализация

`localization.py` — словарь `STRINGS` + `tr(key, lang, **kwargs)`.

UI-языки: **ru**, **en**, **uz**. Каждый ключ обязан иметь все три перевода (тест `test_every_key_has_all_langs`).

Черновик `assets/i18n/uk_be_kk.json` (украинский / белорусский / казахский) **пока не wired** в picker и `normalize_lang`.

---

## 8. Flutter-расширения (`extensions/`)

Ставятся editable (`-e`) из `requirements.txt`. В APK/IPA попадают только после **`flet build`**.

| Пакет | Control | Роль |
|-------|---------|------|
| `flet_local_auth` | `FinanseLocalAuth` | Face ID / face unlock |
| `flet_local_notifications` | `FinanseLocalNotifications` | show + zonedSchedule, haptic, app icon |

После правок Python/Dart плагинов нужна **новая** мобильная сборка.

---

## 9. Связанные документы

- Схема БД — [DATABASE.md](DATABASE.md)  
- Сценарии — [USE_CASES.md](USE_CASES.md)  
- UI — [PRESENTATION.md](PRESENTATION.md)  
- iOS CI — [CODEMAGIC.md](CODEMAGIC.md)  
