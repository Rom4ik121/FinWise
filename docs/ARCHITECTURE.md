# Архитектура FinWise

## 1. Обзор

FinWise считает доходы и расходы, счета, цели, долги, подписки, бюджеты и
курсы валют. UI — Flet поверх Flutter. Код — чистая архитектура:

```
main.py                     → lib.main.run()
lib/core                    — config, SQLite engine, DI, логи
lib/domain                  — сущности, порты репозиториев, use cases
lib/infrastructure          — SQLAlchemy, HTTP, бэкап, биометрия, push, речь
lib/presentation            — страницы Flet, скины, файлы, голосовой ярлык
extensions/                 — Dart-сервисы: local_auth, notifications, speech
```

Зависимости внутрь: presentation и infrastructure зависят от domain.
Реализации портов собирает `build_container()` в `lib/core/dependencies.py`.

## 2. Слои

### 2.1 `lib/core`

| Файл | Назначение |
|---|---|
| `config.py` | Валюта/язык/скин по умолчанию, иконки, `AppConfig`. Пути: Windows — platformdirs; iOS — `~/Library/Application Support/finanse`; Android — `~/finanse` (не `~/.local/share`, иначе PermissionError при старте) |
| `database.py` | Engine, `init_db()`, WAL, `foreign_keys`, патчи колонок SQLite |
| `dependencies.py` | `Container` + `build_container()` |
| `logging_config.py` | Консоль и файл |
| `color_palette.py` | Палитра HEX для счетов и категорий |

### 2.2 `lib/domain`

Сущности (Pydantic): Account, Transaction, Category, Currency, ExchangeRate,
Goal, Debt, Subscription, Budget, AppSettings, Money helpers, `currency_codes`.

Порты: `*Repository` ABC.

Use cases — все `async execute(...)`: транзакции (включая переводы), счета,
цели, долги, подписки, валюты, бюджеты, категории, настройки, JSON-экспорт,
выравнивание валюты единственного счёта.

`domain/services/rate_book.py` — in-memory конвертация по прямым, обратным и
USD-пивот курсам.

### 2.3 `lib/infrastructure`

ORM (`db_models.py`), SQLAlchemy-репозитории (`asyncio.to_thread` +
`session_scope`), HTTP-клиенты курсов, сервисы: бэкап, CSV/PDF, PIN,
биометрия, in-app очередь, OS push, планировщик напоминаний, локализация
(ru/en/uz), сброс данных, распознавание речи и сохранение голосовой операции.

### 2.4 `lib/presentation`

`FinanseApp` — плавающие 4 вкладки, PIN-гейт, secondary-маршруты.
Скины `classic` и `neon` (`presentation/skins/`). Аналитика — один поток
доход+расход (пончики и линия). Экспорт/бэкап на ПК и телефоне —
`file_transfer.py` (обязательно `src_bytes` + копия в выбранный путь).

## 3. Запуск (`lib/main.py`)

Порядок важен для телефонов:

1. Сплэш (только визуальные контролы).
2. Config, логи, `init_db`, DI, сид валют/настроек/счета «Наличные».
3. Фоновые циклы: курсы (`_exchange_rate_loop`), напоминания (`_reminder_loop`).
4. Обработка наступивших подписок.
5. Снять сплэш (`page.controls.clear`).
6. Зарегистрировать **сервисы** на `page.services` (не `page.add`):
   биометрия, локальные уведомления, речь.
7. Запросить разрешение на пуши, поставить OS-напоминания, `FinanseApp.start()`.
8. Ярлык голоса: `install_voice_shortcut` (deep link `finwise://voice`).

`page.web is True` (`flet run --android/--web`) — кастомные Dart-сервисы
не вешаются: иначе красный баннер `Unknown control` и вечный сплэш.
Встроенные FilePicker/Share вешаются с `native_extension=False`.

## 4. DI

`Container` держит репозитории, сервисы и use cases. Несобранный слот —
`None`, имя в `missing`. `require(name)` бросает, если слота нет.
После restore БД: `rebind_session_factory`.

## 5. Данные

SQLite, WAL, FK. `init_db()` = `create_all` + патчи колонок. Alembic —
10 ревизий (см. DATABASE.md).

## 6. Валюты

База — `settings.default_currency`. Fiat: open.er-api.com. Крипто: CoinGecko и
Binance. Курсы Numeric(24,12), `quantize_rate` не обнуляет UZS.

Перевод между счетами в разных валютах конвертирует сумму через RateBook.
Выравнивание единственного счёта при смене валюты отображения **не**
пересчитывает суммы — только код валюты.

## 7. Уведомления

- In-app: `NotificationService.push` (и сразу OS dispatch, если можно).
- OS: Windows — winotify; Android/iOS — `FinanseLocalNotifications`
  (`flutter_local_notifications`). Пакет `flet-android-notifications` в
  зависимости сборки не входит: на iOS он ломает `pub get` (`timezone`
  0.11 против 0.9). Python-fallback остаётся, если пакет установлен вручную.
- `schedule_reminders` ставит in-app события и **zonedSchedule** на 30 дней
  вперёд (срабатывает при закрытом приложении после сборки IPA/APK).
- Цикл Python срабатывает в `reminder_time`, пока процесс жив.
- Тесты: `FINANCE_DISABLE_PUSH=1` (autouse в conftest).

## 8. Безопасность

PIN: PBKDF2, поля `pin_hash` / `pin_salt`. Биометрия только вместе с PIN.
Включение в настройках сразу показывает системный prompt. LockScreen сам
открывает Face ID / отпечаток. Windows Hello через winrt. Тесты:
`FINANCE_BIOMETRIC_OK=1`.

## 9. Файлы

JSON (`ExportDataUseCase`), CSV/PDF (`ExportService`), `.db` (`BackupService`
вместе с WAL/SHM). На desktop `FilePicker.save_file` **обязан** получить
`src_bytes`; затем файл копируется в выбранный путь. Отмена диалога не
маскируется внутренним путём. На телефоне — save/share; restore — выбор
`.db` из файлов.

## 10. Голос

Парсер `voice_parse.parse_voice_expense` (тип, сумма, категория).
Сохранение: `voice_capture.save_spoken_transaction` на первый активный счёт.
Ввод: кнопка в быстром добавлении; hands-free — URL `finwise://voice`
(настройки телефона / Back Tap / Action Button / Routines). Кнопка блокировки
iPhone — Siri, её нельзя отдать приложению. Пока FinWise открыт, зажатие
громкости вниз тоже запускает запись (после сборки с `flet_speech`).

## 11. Скрипты и CI

`scripts/migrate.py`, `seed_demo_data.py`, `build_apk.ps1`, `build_ipa.sh`,
ярлыки, branding. Codemagic и GitHub Actions — см. CODEMAGIC.md.
`flet.toml` / `pyproject.toml`: permissions, splash, iOS usage strings,
deep_linking `finwise` / `voice`.
