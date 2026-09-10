# FinWise — документация

Полное описание приложения **FinWise** (репозиторий `finanse`): локальный учёт личных финансов на **Python 3.11+** и **Flet 0.83–0.86**, данные в **SQLite** на устройстве.

Платформы: **Windows** (desktop), **Android** (APK), **iOS** (IPA). Облачный аккаунт не обязателен.

Репозиторий: [github.com/Rom4ik121/FinWise](https://github.com/Rom4ik121/FinWise)

---

## Оглавление

| Документ | Содержание |
|----------|------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Слои, bootstrap, DI, фоновые циклы, мобильные сервисы, инварианты |
| [ENTITIES.md](ENTITIES.md) | Доменные модели (счета, операции, цели, долги, …) |
| [USE_CASES.md](USE_CASES.md) | Бизнес-сценарии и правила денег / FX / переводов |
| [INFRASTRUCTURE.md](INFRASTRUCTURE.md) | Репозитории, курсы, CCXT, бэкап, PIN/Face ID, push |
| [PRESENTATION.md](PRESENTATION.md) | UI, вкладки, маршруты, формы, UX (splash, lock, count-up) |
| [DATABASE.md](DATABASE.md) | Таблицы SQLite, индексы, Alembic **0001–0027** |
| [PERFORMANCE.md](PERFORMANCE.md) | Скорость БД, FX, UI на телефонах и десктопе |
| [TESTING.md](TESTING.md) | pytest, фикстуры, как гонять тесты |
| [CODEMAGIC.md](CODEMAGIC.md) | Подписанный IPA (iOS) через Codemagic |

Краткий публичный обзор — в корневом [README.md](../README.md).  
Для AI-агентов: [AGENTS.md](../AGENTS.md).

---

## Быстрый старт (Windows)

```powershell
python -m pip install -r requirements.txt
python scripts/migrate.py
python main.py
```

При первом запуске создаются каталог данных, БД и настройки (язык с устройства). Счетов нет — первый счёт создаётся с главного экрана; его валюта становится основной.

**Каталог данных (Windows):**

```text
%LOCALAPPDATA%\finanse\finanse\
```

Внутри: `finanse.db`, `backups/` (в т.ч. `.fwbackup`), `exports/`, `logs/`, `media/`. На desktop — `.secret_box_key`; на iPhone ключ в Keychain.

**Демо-данные:**

```powershell
python scripts/seed_demo_data.py --wipe --scale medium --currency UZS
```

**Тесты:**

```powershell
python -m pytest -q
```

---

## Мобильные сборки

| Платформа | Как собрать | Документ |
|-----------|-------------|----------|
| Android | `.\scripts\build_apk.ps1` | этот README + `flet.toml` |
| iOS | Codemagic workflow `ios-ipa` | [CODEMAGIC.md](CODEMAGIC.md) |

Нативные возможности (**Face ID**, локальные пуши) работают только в **упакованном** APK/IPA.  
`flet run --android` / web — это web-клиент **без** Dart-расширений (так задумано).

После изменений Python-кода плагинов или `extensions/` нужна **новая** сборка.

**Важно:** кастомные Flet Service нельзя добавлять через `page.add()` — на сплэше появится `Unknown control`. Сервисы вешаются на `page.services` (см. `lib/infrastructure/services/flet_services.py`).

Цвет native splash / adaptive icon в `flet.toml` и Codemagic: **`#0B1220`**.

---

## Стек

| Слой | Технологии |
|------|------------|
| UI | Flet (Flutter) |
| Домен | Pydantic v2, чистые use cases |
| Данные | SQLAlchemy 2.0 + SQLite (WAL), Alembic 0001–0027 |
| Сеть | httpx (open.er-api, CoinGecko, Binance), CCXT |
| Отчёты | matplotlib, reportlab |
| Безопасность | PIN (PBKDF), Face ID, AES-GCM secret box для ключей бирж |
| Плагины | `extensions/flet_local_auth`, `flet_local_notifications` |

---

## Структура репозитория

```text
FinWise/
├── main.py                 # точка входа → lib.main.run()
├── lib/
│   ├── core/               # config, БД, DI, логи
│   ├── domain/             # сущности, порты, use cases
│   ├── infrastructure/     # SQLAlchemy, HTTP, OS-сервисы
│   └── presentation/       # экраны и виджеты Flet
├── extensions/             # Flutter-мосты
├── assets/                 # icon, splash, icons/crypto|exchanges, currencies.json
├── migrations/versions/    # Alembic 0001 … 0027
├── scripts/                # migrate, seed, APK, брендинг
├── tests/                  # unit + integration
└── docs/                   # эта документация
```

Черновик локалей uk/be/kk: `assets/i18n/` (пока не в UI).

---

## Жёсткие правила продукта

1. Деньги — только через `quantize_money` (фиат 2 знака, известная крипта — до 8).
2. Переводы — пара операций с общим `transfer_id`; комиссия — отдельный расход «Комиссия» / тег `fee`.
3. Нельзя суммировать разные валюты в «базу» без курса; нет тихого FX-fallback.
4. Все строки UI — через `tr` / `STRINGS` (ru / en / uz).
5. Ошибки пользователю — понятные тексты; traceback и SQL только в логах (`snack_exception`).

Подробности — в [ARCHITECTURE.md](ARCHITECTURE.md) и [USE_CASES.md](USE_CASES.md).
