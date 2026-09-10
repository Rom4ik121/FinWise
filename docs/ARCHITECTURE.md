# Архитектура FinWise

## 1. Назначение

FinWise — **local-first** приложение личного учёта: доходы и расходы, счета (в т.ч. биржи), цели, долги, подписки, бюджеты, мультивалютность и аналитика. UI строится на **Flet** (Flutter). Бизнес-логика отделена от UI и ORM.

Организация пакета: `com.finanse.app`. Имя продукта: **FinWise**.

---

## 2. Слои

```text
main.py  →  lib.main.run()
              │
              ├─ lib/core/             конфиг, SQLite engine, DI, логи
              ├─ lib/domain/           сущности, порты репозиториев, use cases
              ├─ lib/infrastructure/   SQLAlchemy, HTTP, бэкап, биометрия, push
              └─ lib/presentation/     страницы Flet, скины, формы
```

**Правило зависимостей:** `domain` не импортирует Flet и SQLAlchemy.  
Реализации портов собирает `build_container()` в `lib/core/dependencies.py`.  
Presentation и infrastructure зависят от domain, не наоборот.

### 2.1 `lib/core`

| Модуль | Роль |
|--------|------|
| `config.py` | `AppConfig`, валюта/язык/скин по умолчанию, каталоги данных, списки иконок |
| `database.py` | Engine, `init_db()` (create_all + патчи колонок + индексы + best-effort Alembic) |
| `dependencies.py` | `Container`, `build_container()` |
| `logging_config.py` | Консоль и файл в `logs/` |
| `color_palette.py` | HEX-палитра для счетов и категорий |

**Пути данных (`AppConfig`):**

| Платформа | Поведение |
|-----------|-----------|
| Windows | `platformdirs` → обычно `%LOCALAPPDATA%\finanse\finanse\` |
| iOS | `FLET_APP_STORAGE_DATA` / аналоги, иначе `~/Library/Application Support/finanse` |
| Android | Только **writable** sandbox: env Flet storage, `/data/user/0/com.finanse.app/files/finanse` и т.п. **Не** произвольный `~/finanse` на корне `/data` |

### 2.2 `lib/domain`

- **entities/** — Pydantic-модели (см. [ENTITIES.md](ENTITIES.md)).
- **repositories/** — ABC-порты.
- **use_cases/** — сценарии с `async execute(...)` (см. [USE_CASES.md](USE_CASES.md)).
- **services/** — `RateBook`, кэш курсов.
- **unit_of_work.py** — `unit_of_work` / `in_unit_of_work` для атомарных multi-step сценариев (транзакции, списания подписок и т.п.); infra `_base.py` только re-export.
- **transaction_paging.py** — постраничная загрузка ledger (`page_size=500`, `max_rows=25_000`).
- **exchanges.py** — каталог поддерживаемых бирж и метаданные иконок.

### 2.3 `lib/infrastructure`

ORM (`db_models.py`), репозитории на SQLAlchemy (`asyncio.to_thread` + session), HTTP-клиенты курсов и CCXT, сервисы ОС и безопасности (см. [INFRASTRUCTURE.md](INFRASTRUCTURE.md)).

### 2.4 `lib/presentation`

`FinanseApp` — оболочка: 4 вкладки, PIN/Face ID-гейт, secondary-маршруты, скины Classic/Neon (см. [PRESENTATION.md](PRESENTATION.md)).

### 2.5 `extensions/`

Dart/Flutter-мосты, подключаемые только в нативной сборке:

- `flet_local_auth` — Face ID / face unlock  
- `flet_local_notifications` — локальные пуши + haptic (иконка `@mipmap/ic_launcher`)  

---

## 3. Bootstrap (`lib/main.py`)

Порядок важен для телефонов (избежать белого экрана и «Unknown control»):

1. **Loading** — `before_main` → `prepare_launch_page`: тёмный фон `#0B1220`, `ProgressRing`, «Загрузка…» (`build_launch_splash`). Только визуальные контролы; native splash в сборках отключён.
2. Config → логирование → `init_db` → `build_container(..., init_database=False)`.
3. `_seed_if_needed` — upsert валют из `assets/data/currencies.json` и настройки (язык с устройства; валюта — после первого счёта).
4. Фоновые задачи на `page.run_task`:
   - `_exchange_rate_loop` — обновление курсов по интервалу из настроек;
   - `_reminder_loop` — ежедневный sweep напоминаний;
   - `_daily_backup_loop` — раз в час проверка; запись `finanse_daily.db` **не чаще одного раза в локальные сутки**.
5. Регистрация сервисов на **`page.services`** (не `page.add`): local auth, notifications.
6. `FinanseApp.start()` — тема, PIN-гейт, навигация, UI.
7. Post-start (после первого кадра, с паузой ~1с на iOS):
   - **запрос разрешения на уведомления** — не в `initialize()` плагина (iOS глотает диалог на splash);
   - повтор на lifecycle `resume`/`show`;
   - подтверждение OS-баннером (`push.ready`), если разрешение выдано;
   - daily backup, `process_due_subscriptions`, `schedule_reminders`.

На `page.web is True` (`flet run --android` / web) нативные Dart-сервисы не вешаются.

---

## 4. Dependency Injection

`Container` в `lib/core/dependencies.py` держит:

- репозитории (account, transaction, goal, debt, subscription, currency, category, settings, budget, exchange_connection);
- сервисы (encryption, backup, export, notification, rate provider, …);
- use cases (`add_transaction`, `transfer_between_accounts`, `list_accounts`, …).

Несобранный слот остаётся `None` — UI должен проверять наличие перед вызовом.

---

## 5. Безопасность (обзор)

| Механизм | Где |
|----------|-----|
| PIN | Хэш/соль в `settings`; use cases `Get/Set/ClearPinCredentials`; экран `LockScreen`. После set/clear/restore/wipe PIN **перечитывается** (`AppState.reload_pin_gate`), иначе фоновая блокировка использовала бы хэш со старта сессии. |
| Face ID | Только face/iris на мобильных (отпечаток / Windows Hello fingerprint **не** предлагаются; desktop → PIN) |
| Автоблокировка | После ≥ **15 с** в фоне на мобильных (`app.py`) |
| Ключи бирж | AES-GCM (`secret_box`, файл `.secret_box_key`) |
| Ошибки UI | `user_facing_error` / `snack_exception`: доменные English → i18n; сырой technical → `error.generic`; без traceback |

---

## 6. Инварианты денег и FX

1. **`quantize_money`** — единая квантизация сумм.
2. Баланс счёта = `initial_balance` + Σ доходы − Σ расходы (включая ноги переводов и комиссии).
3. **Перевод** — две операции с одним `transfer_id` (расход + доход), категория «Перевод»; в бюджетах/статистике операций обычно исключаются.
4. **Комиссия** — отдельный расход «Комиссия», тег `fee` (на счёте списания).
5. **FX:** конвертация только через `RateBook` / курсы; при отсутствии курса — явный отказ пользователю, без «тихой» подмены.
6. Нельзя складывать суммы в разных валютах как «итого в базе» без конвертации.

---

## 7. Локализация и тема

- UI-языки: **ru**, **en**, **uz** (`SUPPORTED_LANGS`, picker в Settings).
- Строки: словарь `STRINGS` + `tr(key, lang, **kwargs)`. Черновик `assets/i18n/uk_be_kk.json` (uk/be/kk) **не подключён**.
- Тема: light / dark / system.
- UI style: **classic** (по умолчанию в рантайме скинов) / **neon** (дефолт в `config` может отличаться — см. `DEFAULT_UI_STYLE` в `config.py`).

---

## 8. Связанные документы

- Модели — [ENTITIES.md](ENTITIES.md)  
- Сценарии — [USE_CASES.md](USE_CASES.md)  
- Схема БД — [DATABASE.md](DATABASE.md)  
- UI — [PRESENTATION.md](PRESENTATION.md)  
