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
- После разблокировки открывается основной UI.

### Deep link

`finwise://app` — deep link схема приложения (без голосового ярлыка).

---

## 2. Состояние (`state/app_state.py`)

Observer: `subscribe` / `notify` (с coalesce).

| API | Смысл |
|-----|--------|
| `bump_refresh(*scopes)` | Точечная перерисовка страниц |
| `ui_style`, язык, валюта | Тема и локаль |
| Lock | Безопасность |

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
| Dashboard | `pages/dashboard.py` | Баланс, день, быстрые действия, бюджеты, бейджи, график (prefs hide/days); toggles in-place mutate |
| Transactions | `pages/transactions.py` | Поиск (FTS `query=`), фильтры, группировка, CRUD, перевод, частый счёт |
| Accounts | `pages/accounts.py` | Список счетов, биржи, корпоративные workspace |
| Account detail | `pages/account_detail.py` | История, статистика, графики счёта; быстрый расход/доход; перевод; PDF-отчёт за период; детали tx с фото |
| Analytics | `pages/analytics.py` | Категории дохода/расхода + линия за период (пустые дни — нули) |
| Goals / Debts / Subscriptions / Budgets / Currencies | соответствующие `pages/` | CRUD и профили; списки через `layout.make_v_scroll` |
| Settings | `pages/settings.py` | Тема, скин, язык, валюта, пуши, PIN/Face ID, голос, экспорт, бэкап, сброс, **обучение** |

### UX-детали

- **Count-up** денежных сумм при Refresh: `count_up.py` (`mark_money_text` / `play_count_ups`) на dashboard, accounts, transactions, analytics, account detail. Скрытый баланс и простые % KPI не анимируются.
- **Частый счёт** для дохода/расхода: `frequent_account.py` — самый используемый не-transfer счёт; подпись «часто» в quick-add и редакторе операций.
- **Reload coalesce:** `reload_gate.py` — поиск/фильтры не штормят БД.
- **Scroll / rebuild:** `ui_motion.replace_controls` сохраняет позицию списка.
- Ошибки: `snack_exception` / `user_facing_error` — доменные тексты → i18n; technical English → `error.generic`; без traceback.
---

## 6. Виджеты (`widgets/`)

Карточки счетов / операций / целей / долгов / подписок;  
`QuickAddSheet` (в т.ч. микрофон); `TransferSheet`; `CategoryPicker`; `CurrencyTickerPicker`;  
`DateTimeField`; `LockScreen`; Splash; Charts (пончик, линия);  
`DualAddButton`; ConfirmDialog; FullscreenForm; `LineItemsEditor`;  
`pdf_export_sheet` — период, счета и разделы PDF-отчёта.

Клавиатура форм: `form_keyboard.py`. Ввод сумм: `money_input.py`.

---

## 7. Файлы (`file_transfer.py`)

- Экспорт: `offer_saved_file` → `save_file(..., src_bytes=...)` → `materialize_saved_file`.  
  Отмена пользователя → `None`, без ложного «успеха».
- Телефон: share sheet.
- Restore: `pick_files(with_data=True)`, классификация sqlite / json.

---

## 8. Утилиты presentation

| Модуль | Роль |
|--------|------|
| `responsive.py` | `scale_font`, `tap_*`, `clamp_content_width`, `calendar_cell_size`, `compact_chart_size`, breakpoints |
| `utils.py` | `format_money`, `run_async`, `snack`, RateBook helpers, `user_facing_error`, `snack_exception` |
| `tx_query.py` | Paged load транзакций (500 / 25k) через use case |
| `reload_gate.py` | Coalesce частых reload |
| `ui_motion.py` | `replace_controls`, scroll memory, animate flag |
| `haptics.py` | Лёгкий haptic на успех (mobile) |
| `icon_registry.py` / `account_icons.py` | Иконки и валютные глифы |
| `analytics_period.py` | `enumerate_period_keys`, `fill_time_series` |
| `notification_badges.py` | Бейджи pending |
| `dropdown_options.py` / `currency_options.py` | Опции форм |
| `layout.py` | `make_v_scroll`, chip rows + re-export responsive API |
| `widgets/period_scale.py` | Шкала периода на summary rings |

### Responsive / touch (2026-09-04)

- Шрифты заголовков через `scale_font` (SE…Pro Max).
- Touch targets ≥ **40** logical px (`tap_button_style`, calendar cells, nav pads).
- Формы / lock: `clamp_content_width` вместо жёстких `width=280/340`.
- Графики: `chart_layout` / `compact_chart_size` от `page.width/height`.
- ПК и мобильные: одна floating bottom nav (sidebar нет — паритет полный).

---

## 10. Связанные документы

- Bootstrap и слои — [ARCHITECTURE.md](ARCHITECTURE.md)  
- Сервисы — [INFRASTRUCTURE.md](INFRASTRUCTURE.md)  
- Сценарии — [USE_CASES.md](USE_CASES.md)  
