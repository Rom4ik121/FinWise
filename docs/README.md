# FinWise — документация

Кроссплатформенный учёт личных финансов: **Python 3.11+**, **Flet 0.83–0.86**, SQLite.
Платформы: Windows (desktop), Android и iOS (упакованный IPA/APK).

## Разделы

| Файл | Содержание |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Слои, запуск, DI, данные, валюты, уведомления, безопасность, мобильные плагины |
| [ENTITIES.md](ENTITIES.md) | Доменные модели |
| [USE_CASES.md](USE_CASES.md) | Сценарии (транзакции, счета, цели, долги, подписки, бюджеты, экспорт) |
| [INFRASTRUCTURE.md](INFRASTRUCTURE.md) | Репозитории, API курсов, бэкап, push, биометрия, речь |
| [PRESENTATION.md](PRESENTATION.md) | UI, навигация, скины, голосовой ввод, файлы |
| [DATABASE.md](DATABASE.md) | SQLite, таблицы, индексы, миграции Alembic 0001–0016 |
| [PERFORMANCE.md](PERFORMANCE.md) | Оптимизация БД/FX/UI для телефонов и десктопа |
| [TESTING.md](TESTING.md) | pytest, фикстуры, покрытие |
| [CODEMAGIC.md](CODEMAGIC.md) | Сборка подписанного IPA |

## Быстрый старт (Windows)

```powershell
python -m pip install -r requirements.txt
python scripts/migrate.py
python main.py
```

Первый запуск создаёт каталог данных, БД, настройки и счёт «Наличные».
Windows: `%LOCALAPPDATA%\finanse\finanse\`.

Демо-данные:

```powershell
python scripts/seed_demo_data.py --wipe --scale medium --currency UZS
```

Тесты:

```powershell
python -m pytest -q
```

## Телефоны (IPA / APK)

Нативные функции (биометрия, пуши, микрофон, ярлык `finwise://voice`) есть
только в **собранном** приложении. `flet run --android` открывает web-клиент
без Dart-расширений — так и задумано.

После изменения Python/Flutter-плагинов нужна **новая сборка** IPA и APK.
Не добавляйте кастомные Flet Service в `page.add()`: клиент рисует
`Unknown control` на сплэше и приложение не открывается. Сервисы вешаются
на `page.services`.

Разрешения и deep link задаются в `pyproject.toml` / `flet.toml`.
IPA: [CODEMAGIC.md](CODEMAGIC.md). APK: `.\scripts\build_apk.ps1`.

## Стек

- UI: Flet (Flutter)
- Данные: SQLAlchemy 2.0 + SQLite (WAL), Alembic
- Модели: Pydantic v2
- Курсы: httpx (open.er-api, CoinGecko, Binance)
- Отчёты: matplotlib, reportlab
- Плагины: `extensions/flet_local_auth`, `flet_local_notifications`, `flet_speech`

## Структура репозитория

```
finanse/
├── main.py / lib/main.py     — вход и bootstrap
├── lib/core                  — config, БД, DI
├── lib/domain                — сущности, порты, use cases
├── lib/infrastructure        — SQLAlchemy, HTTP, OS-сервисы
├── lib/presentation          — Flet UI
├── extensions/               — Flutter-мосты (биометрия, пуши, речь)
├── migrations/               — Alembic (10 ревизий)
├── assets/                   — иконки, currencies.json
├── scripts/                  — migrate, seed, APK/IPA
├── tests/                    — unit + integration
└── docs/                     — эта документация
```
