# Презентация (Flet UI)

Код: `lib/presentation/`. Оболочка — `FinanseApp` в `app.py`.  
Все пользовательские строки — через `tr` / `STRINGS`.

---

## 1. Оболочка (`app.py`)

### Навигация

- Четыре **основные вкладки**: Главная, Операции, Счета, Настройки.
- Кастомный **floating NavigationBar** (не scaffold NavigationBar).
- Контент через `AnimatedSwitcher`, кэш построенных страниц.
- **Вторичные маршруты** (состояние приложения, не URL):

| Маршрут | Экран |
|---------|--------|
| `analytics` | Аналитика |
| `account:{id}` | Карточка счёта |
| `goals` | Цели |
| `debts` | Долги |
| `subscriptions` | Подписки |
| `currencies` | Валюты |
| `budgets` | Бюджеты |

API состояния: `set_tab`, `open_secondary`, `close_secondary`.

### Блокировка

- При наличии PIN — `LockScreen` до разблокировки.
- **Face ID** (если включено и доступно) + PIN; fingerprint не предлагается.
- На мобильных: после ≥ **15 с** в фоне — снова lock (`_BACKGROUND_LOCK_SECONDS`).
- После разблокировки может сработать отложенный голосовой захват (`pending_voice_capture`).

### Deep link

`finwise://voice` → `voice_shortcut.install_voice_shortcut` (цепочка с lifecycle lock).

---

## 2. Состояние (`state/app_state.py`)

Observer: `subscribe` / `notify` (с coalesce).

| API | Смысл |
|-----|--------|
| `bump_refresh(*scopes)` | Точечная перерисовка страниц |
| `ui_style`, язык, валюта | Тема и локаль |
| Lock / pending voice | Безопасность и голос |

Страницы подписываются на refresh и обновляют данные без полного рестарта приложения.

---

## 3. Скины (`skins/`)

| Скин | Вид |
|------|-----|
| `classic` | Системная светлая/тёмная тема |
| `neon` | Тёмно-серый градиент, стекло (`glass_layer` + Blur), акценты |

Выбор: `settings.ui_style`. Тема light/dark/system — отдельно.

Тема Material / цвета: `theme.py`, `styles.py`.

---

## 4. Splash

`widgets/splash_screen.py` → `build_launch_splash`:

- Градиент **`#0B1220` → `#121A2B`**
- Material-иконка кошелька (`ACCOUNT_BALANCE_WALLET`)
- Заголовок **FinWise**
- Разделитель + `ProgressRing`
- **Без** слогана «Личный учёт финансов»

Native splash / adaptive icon в `flet.toml` и Codemagic: `#0B1220`.  
Скрипт `scripts/build_apk.ps1` может ещё передавать `#000000` — при сборке APK предпочтительно выровнять цвет под бренд.

---

## 5. Страницы

| Страница | Файл | Содержание |
|----------|------|------------|
| Dashboard | `pages/dashboard.py` | Баланс, день, быстрые действия, бюджеты, бейджи, график (prefs hide/days) |
| Transactions | `pages/transactions.py` | Поиск, фильтры, группировка, CRUD, перевод, частый счёт |
| Accounts | `pages/accounts.py` | Список счетов, биржи |
| Account detail | `pages/account_detail.py` | История, статистика, графики счёта |
| Analytics | `pages/analytics.py` | Категории дохода/расхода + линия за период (пустые дни — нули) |
| Goals / Debts / Subscriptions / Budgets / Currencies | соответствующие `pages/` | CRUD и профили |
| Settings | `pages/settings.py` | Тема, скин, язык, валюта, пуши, PIN/Face ID, голос, экспорт, бэкап, сброс |

### UX-детали

- **Count-up** денежных сумм при Refresh: `count_up.py` (`mark_money_text` / `play_count_ups`) на dashboard, accounts, transactions, analytics, account detail. Скрытый баланс и простые % KPI не анимируются.
- **Частый счёт** для дохода/расхода: `frequent_account.py` — самый используемый не-transfer счёт; подпись «часто» в quick-add и редакторе операций.
- Ошибки: `snack_exception` / `user_facing_error` — без traceback.

---

## 6. Виджеты (`widgets/`)

Карточки счетов / операций / целей / долгов / подписок;  
`QuickAddSheet` (в т.ч. микрофон); `TransferSheet`; `CategoryPicker`; `CurrencyTickerPicker`;  
`DateTimeField`; `LockScreen`; Splash; Charts (пончик, линия);  
`DualAddButton`; ConfirmDialog; FullscreenForm; `LineItemsEditor`.

Клавиатура форм: `form_keyboard.py`. Ввод сумм: `money_input.py`.

---

## 7. Файлы (`file_transfer.py`)

- Экспорт: `offer_saved_file` → `save_file(..., src_bytes=...)` → `materialize_saved_file`.  
  Отмена пользователя → `None`, без ложного «успеха».
- Телефон: share sheet.
- Restore: `pick_files(with_data=True)`, классификация sqlite / json.

---

## 8. Голос (`voice_shortcut.py`)

Маршруты `finwise://voice` / `/voice`.  
Пока приложение открыто, плагин речи может поднять `on_voice_request` (в т.ч. долгое зажатие громкости вниз на поддерживаемых устройствах).

Примеры фраз: «расход такси 500», «доход зарплата 2 млн».

---

## 9. Утилиты presentation

| Модуль | Роль |
|--------|------|
| `utils.py` | `format_money`, `run_async`, `snack`, RateBook helpers, `user_facing_error`, `snack_exception` |
| `haptics.py` | Лёгкий haptic на успех (mobile) |
| `icon_registry.py` / `account_icons.py` | Иконки и валютные глифы |
| `analytics_period.py` | `enumerate_period_keys`, `fill_time_series` |
| `notification_badges.py` | Бейджи pending |
| `dropdown_options.py` / `currency_options.py` | Опции форм |
| `layout.py` | Общие отступы / ширина |

---

## 10. Связанные документы

- Bootstrap и слои — [ARCHITECTURE.md](ARCHITECTURE.md)  
- Сервисы — [INFRASTRUCTURE.md](INFRASTRUCTURE.md)  
- Сценарии — [USE_CASES.md](USE_CASES.md)  
