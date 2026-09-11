# FinWise

**Локальный учёт личных финансов** для Windows, Android и iOS.  
Данные хранятся на устройстве (SQLite) — без обязательного облака и аккаунтов.

<p align="center">
  <img src="assets/icon.png" alt="FinWise" width="120" />
</p>

---

## Что умеет

| Раздел | Возможности |
|--------|-------------|
| **Главная** | Общий баланс, доход/расход за день, быстрый доход/расход, аналитика |
| **Операции** | Доходы, расходы, переводы, комиссии, теги, позиции чека, поиск и фильтры, импорт CSV |
| **Счета** | Наличные, карты, крипто, подключение бирж (CCXT), синхронизация |
| **Цели** | Накопления с пополнением со счёта |
| **Долги** | Долги мне / я должен, погашения |
| **Подписки** | Регулярные платежи и напоминания |
| **Шаблоны** | Повторяющиеся доходы/расходы с автосозданием |
| **Бюджеты** | Лимиты по категориям на месяц, пороги 80%/100% |
| **Аналитика** | Поток, капитал во времени, цели, долги, подписки, бюджеты |
| **Валюты** | Фиат + крипто, курсы, конвертация без «тихих» ошибок FX |
| **Безопасность** | PIN + Face ID, автоблокировка после свёрнутого приложения |
| **Резерв** | Ежедневное обновление одной автоматической резервной копии |

Интерфейс: **18 языков** (в т.ч. русский, English, українська, Deutsch, Português, 简体中文…), язык с устройства при первом запуске, светлая и тёмная темы, скины Classic / Neon.

---

## Быстрый старт (Windows)

```powershell
python -m pip install -r requirements.txt
python scripts/migrate.py
python main.py
```

Каталог данных:

```text
%LOCALAPPDATA%\finanse\finanse\
```

Демо-данные:

```powershell
python scripts/seed_demo_data.py --wipe --scale medium --currency UZS
```

Тесты:

```powershell
python -m pytest -q
```

---

## Стек

- **UI:** [Flet](https://flet.dev) 0.83–0.86 (Flutter)
- **Данные:** SQLAlchemy 2 + SQLite (WAL), Alembic
- **Модели:** Pydantic v2
- **Курсы:** httpx (open.er-api, CoinGecko, Binance)
- **Биржи:** CCXT
- **Мобильные плагины:** биометрия, локальные уведомления (`extensions/`)

Архитектура — чистые слои:

```text
main.py
 └─ lib/core/            конфиг, БД, DI
 └─ lib/domain/          сущности и use cases (без Flet/SQLAlchemy)
 └─ lib/infrastructure/  репозитории, API, OS-сервисы
 └─ lib/presentation/    экраны и виджеты Flet
```

---

## Структура репозитория

```text
FinWise/
├── main.py                 # точка входа
├── lib/                    # приложение
├── extensions/             # Flutter-мосты (Face ID, push)
├── assets/                 # иконки, splash, currencies.json, i18n overlays
├── migrations/             # Alembic 0001…0029
├── scripts/                # migrate, seed, APK/IPA
├── tests/                  # unit + integration
└── docs/                   # подробная документация
```

Документация: **[docs/README.md](docs/README.md)**  
(архитектура, сущности, use cases, БД, производительность, Codemagic)

---

## Сборка на телефон

Нативные функции (Face ID, пуши) работают в **собранном** APK/IPA.  
`flet run --android` — web-клиент без Dart-плагинов.

**Android (APK):**

```powershell
.\scripts\build_apk.ps1
```

**iOS (IPA):** [docs/CODEMAGIC.md](docs/CODEMAGIC.md) — Ad Hoc (`ios-ipa`) or App Store / TestFlight (`ios-appstore`). GitHub Actions does **not** produce a signed IPA.

---

## Безопасность данных

- База и ключи только в локальном каталоге приложения
- API-ключи бирж шифруются (`secret_box`; на iPhone — Keychain). Резервная копия `.fwbackup` включает базу, ключ и фото; старые `.db` по-прежнему восстанавливаются
- PIN: 4–8 цифр; после установки PIN фоновая блокировка на iPhone начинает работать в той же сессии
- В git не попадают: `.env`, `*.db`, `secrets/`, ключи и профили подписи (см. `.gitignore`)

---

## Для разработчиков / агентов

Краткий вход: [AGENTS.md](AGENTS.md)

Правила продукта:

- деньги только через `quantize_money`
- переводы через `transfer_id`, комиссии — отдельный расход
- не суммировать разные валюты в «базу» без курса
- пользовательские строки — через `tr` / `STRINGS` (18 LTR языков; недостающие ключи → en)
- ошибки в UI — понятные тексты (`user_facing_error`); технические детали только в логах
- тяжёлые выборки ledger — через paging (не unbounded `list`)

---

## Лицензия и автор

Репозиторий: [github.com/Rom4ik121/FinWise](https://github.com/Rom4ik121/FinWise)

---

<p align="center">
  <b>FinWise</b> — личные финансы под контролем, данные у вас.
</p>
