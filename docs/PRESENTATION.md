# Презентация (Flet UI)

Код: `lib/presentation/`. Оболочка — `FinanseApp` в `app.py`.  
Экраны: публичный импорт `lib.presentation.views`.  
Переиспользуемые виджеты: `lib.presentation.components` (cards / dialogs / inputs / layout).  
Реализации карточек пока в `widgets/` — `components/` это группированный API.  
Все пользовательские строки — через `tr` / `STRINGS`.

---

## 1. Оболочка (`app.py`)

### Навигация

- Четыре **основные вкладки**: Главная, Операции, Счета, Настройки.
- Кастомный **floating NavigationBar**. Оболочка — `Stack` (`StackFit.EXPAND`, clip NONE) с `_content_pane` **ltrb=0 + expand** (не LOOSE unpositioned expand → height 0 на xs). `is_compact` — ширина **≤420**. Compact: без nav blur, `AnimatedSwitcher` duration 0. **Windows blank body:** (1) `page.width` и `window.width` оба могут отставать — `note_viewport_size` кэширует `e.width` *до* inset math. (2) `page_header` / `form_header_bar` **не** `wrap` на Row с `expand=True`. Gutters ≤ `(width - min(240,width))/2`. `NARROW_MAX=400`, overlay height ≤ 18% окна.
- Кэш построенных страниц.
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
| `import_csv` | Импорт CSV-выписки |
| `recurring` | Шаблоны повторяющихся операций |

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
| `ui_style`, язык, валюта | Тема и локаль (язык с устройства до выбора в Settings) |
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

`widgets/splash_screen.py` → `prepare_launch_page` / `build_launch_splash`:

- Тёмный градиент **`#0B1220` → `#121A2B`**
- `ProgressRing` + «Загрузка…» (без дублирующей бренд-заставки)
- `before_main` в `lib/main.py` + `page.window.bgcolor` — без белой вспышки
- Native splash в сборках **отключён** (`[tool.flet.splash] android/ios/web = false`); adaptive icon: `#0B1220`  
Скрипт `scripts/build_apk.ps1` может ещё передавать `#000000` — при сборке APK предпочтительно выровнять цвет под бренд.

---

## 5. Страницы

| Страница | Файл | Содержание |
|----------|------|------------|
| Dashboard | `pages/dashboard.py` (`views`) | Баланс, день, быстрые действия, бюджеты, бейджи, график; `page_frame` + слоты |
| Операции | `pages/transactions.py` | Поиск (FTS `query=` по категории/комментарию/тегам/payee/сумме), фильтры (счёт, тип, даты, сумма) — панель Tune с Apply/Clear, persist, импорт CSV; `page_frame` |
| Accounts | `pages/accounts.py` | Список счетов (`card_grid` 1–3 колонки), биржи, корпоративные workspace |
| Account detail | `pages/account_detail.py` | История, статистика, графики счёта; быстрый расход/доход; перевод; PDF-отчёт за период; детали tx с фото; `page_frame` |
| Analytics | `pages/analytics.py` | Поток, капитал во времени (снимки), цели, долги, подписки, бюджеты; `page_frame` |
| Goals / Debts / Subscriptions / Recurring / Budgets / Currencies / CSV import | соответствующие `pages/` | CRUD и профили; `page_frame` + `card_grid` (1–2 колонки) |
| Settings | `pages/settings.py` | Тема, скин, язык (18 LTR, эндонимы), валюта, пуши, пороги бюджета, PIN/Face ID, экспорт, бэкап, сброс; `page_frame` |

### UX-детали

- **Адаптив карточек:** шрифты, кольца и диаграммы считаются от **внутренней ширины блока** (`fit_font` / `hero_block_metrics` / `kpi_card_metrics`), а не от окна. KPI в ряду из 2–3 ячеек сжимаются. В donut процент / сумма / «Всего» — `donut_center_metrics` (меньше, чем подпись ProgressRing).
- **Count-up** денежных сумм и графики на **кнопке Обновить**. Герой «Общий баланс» на главной всегда полный (`figure_only` без compact), не 8.7M. Пассивный reload после сохранения только подставляет цифры.
- **Частый счёт** для дохода/расхода: `frequent_account.py` — самый используемый не-transfer счёт; подпись «часто» в quick-add и редакторе операций.
- **Reload coalesce:** `reload_gate.py` — поиск/фильтры не штормят БД; скрытые вкладки не reload'ятся на каждый save (явный `mark_shown` / `mark_hidden`).
- **Scroll / rebuild:** `ui_motion.replace_controls` сохраняет позицию списка. Главная при повторном reload мутирует слоты (баланс/ярлыки/бюджеты), не пересобирает ListView. Fullscreen-формы reuse'ят один overlay-слот (`push_overlay`); закрытие обнуляет дерево без `page.update()`.
- Ошибки: `snack_exception` / `user_facing_error` — доменные тексты → i18n; technical English → `error.generic`; без traceback. Пустой Save на формах (счета, операции, долги, цели, подписки, бюджеты) не молчит: `form_validation.py` ставит `TextField.error` и красный тост поверх fullscreen (`ui_feedback.flash_error`).
- Списки: нижний padding ListView (`LIST_NAV_CLEARANCE` = 104 px), чтобы контент не прятался под floating nav / home indicator.
- Категория из операции: `CategoryPicker` открывает полноценный редактор (имя / иконка / цвет), кнопка «Создать» сверху списка.
---

## 6. Компоненты (`components/` + `widgets/`)

Публичный kit: `lib.presentation.components` — карточки, диалоги, инпуты, `adaptive_text` / `money_label` / `card_grid` / `page_frame` / `card_with_actions`.  
Реализации: карточки счетов / операций / целей / долгов / подписок в `widgets/`.  
`QuickAddSheet`; `TransferSheet`; `CategoryPicker`; `CurrencyTickerPicker`;  
`AccountStripPicker` — круговая карусель счетов (иконка, цвет, название, баланс; листание замыкается) в формах операций / переводов / целей / долгов / подписок; `DateTimeField` — горизонтальная лента дней текущего месяца + полноэкранный календарь (`push_overlay`); в сетке видны все 7 дней недели и числа соседних месяцев.  
`DualAddButton`; ConfirmDialog; FullscreenForm; `LineItemsEditor`;  
`pdf_export_sheet` — период, счета и разделы PDF-отчёта; кнопка **Экспорт PDF** закреплена внизу листа (в шапке — компактная иконка). Сборка PDF идёт в фоне (`asyncio.to_thread`), matplotlib только с backend **Agg**.

Клавиатура форм: `form_keyboard.py`. Ввод сумм: `money_input.py` (caret всегда в конце при группировке, иначе «50» схлопывается в «5»). Валидация: `form_validation.py`.

---

## 7. Файлы (`file_transfer.py`)

- Экспорт: `offer_saved_file` → `save_file(..., src_bytes=...)` → `materialize_saved_file`.  
  Отмена пользователя → `None`, без ложного «успеха».
- Телефон: share sheet.
- Restore: `pick_files(with_data=True)`, классификация `.fwbackup` / sqlite / json / `.key`.

---

## 8. Утилиты presentation

| Модуль | Роль |
|--------|------|
| `responsive.py` | Breakpoints xs–xl, `layout_width` / `shell_max_width`, `wrap_safe_area`, `scale_font` / `scale_size`, `grid_columns`, `tx_tile_metrics`, `entity_card_metrics`, `content_inset`, `nav_chrome_metrics` |
| `utils.py` | `format_money`, `run_async`, `snack` (успех и ошибка → top toast), RateBook helpers, `user_facing_error`, `snack_exception` |
| `form_validation.py` | Имя / сумма: поле + тост, видно над fullscreen |
| `ui_feedback.py` | Зелёный/красный chip поверх overlay |
| `tx_query.py` | Paged load транзакций (500 / 25k) через use case |
| `reload_gate.py` | Coalesce частых reload |
| `ui_motion.py` | `replace_controls`, scroll memory, ease-out tokens (150–280ms), Reduce Motion, press scale, `wrap_enter` / `chart_enter`, overlay enter stamp |
| `haptics.py` | Light impact on taps / success / error; cooldown so it never spam-buzzes |
| `icon_registry.py` / `account_icons.py` | Иконки и валютные глифы |
| `analytics_period.py` | `enumerate_period_keys`, `fill_time_series` |
| `notification_badges.py` | Бейджи pending |
| `dropdown_options.py` / `currency_options.py` | Опции форм |
| `category_lookup.py` | NFC + casefold lookup of catalog icons for tiles |
| `layout.py` | `make_v_scroll`, chip rows + re-export responsive API |
| `widgets/period_scale.py` | Шкала периода на summary rings |

### Responsive / touch (2026-09-10)

- Шрифты, паддинги, иконки и высота плиток через `scale_font` / `scale_size` / `entity_card_metrics` от **ширины колонки** (`layout_width`), не сырого окна.
- Все экраны — `page_frame` с **маленьким** gutter (8/12). Центрирование lg/xl делает **оболочка** (`shell_side_padding`, обновляется на resize) — иначе stale 200px inset + `HARD_EDGE` обнуляет body при сжатии окна до 320 без remount. SafeArea только на iOS/Android.
- **xs (~320–390):** `NARROW_MAX=400`; оболочка **Stack** с fill-positioned pane. Заголовок — `wrap=False` на Row с `expand=True` (ellipsis на title). `clamp_content_width` никогда не шире viewport; nav margin/label уже; tap ≥ **44**; dual-add в списке; ListView `HARD_EDGE`. Resize 390→375 пересобирает layout (≥8 px на xs).
- **sm (~400–420):** основные поля — gutter 12 px.
- Суммы и названия карточек: `adaptive_text` / `money_label` с ellipsis.
- Touch targets ≥ **44** logical px (`tap_button_style`, calendar cell **height**, nav pads, account/tx chevrons). Calendar **width** uses `calendar_day_width` so all 7 weekdays fit on SE.
- Motion: overlays fade/slide; cards scale to 0.98 on press; toasts ease in from the top. Tab bodies do **not** fade (`AnimatedSwitcher` stuck at opacity 0 / height 0 on Windows). iOS Reduce Motion / `FINANCE_REDUCE_MOTION=1` skips animation. Neon glass blur is capped (~8–10) so it does not strain the eyes.
- Charts (analytics / account / dashboard) fade+slide in on first paint and manual refresh only — silent `ReloadGate` reloads skip to avoid jank. PDF export chips/actions and icon/color pickers use the same press + selection haptic language. Settings accordion eases expand/collapse (opacity + scale, delayed hide). Lock screen stays static.
- Amount fields: live grouping must not `update()` on every keystroke (Flet web caret-at-0 turns `50` into `05`→`5`). `repair_amount_caret_prepend` treats a one-digit prepend as an append, including a missed first `on_change` (`""` → `"05"` → `"50"`). After a programmatic write, ignore the echoed extra digit for ~120ms so `50` does not flash as `500`.
- Settings language: fullscreen endonym list (`LanguagePicker`, English first) — not a Dropdown (Flet menus clip/scroll away `en`).
- First-run default currency follows the device **region** (`uk-UA` → UAH) until Settings save or the first account (`currency_user_set`). The new-account ticker uses `settings.default_currency`.
- Transactions Tune: filter panel (account / type / category / period / amount) with header **Apply**; period chips only fill dates; **Clear** is explicit. Opening Tune does not wipe filters.
- Success toasts linger ~2.3s (`ui_feedback._BANNER_MS`) and stay above fullscreen overlays. Fullscreen sheets insert **under** the toast; dismissed sheets set `ignore_interactions` immediately. Native enter fades from `opacity=0` with `ignore_interactions` until the resting pose; Flet web never uses `opacity=0` overlays (they still steal taps). Settings accordion skips the fade on web and ignores hits while collapsed. Account Edit/Delete sit outside the card’s open-detail hit target. On xs, form Save is a compact 44px icon so the title is not crushed.
- Template chips (budget / debt / goal / subscription) fill the amount only when the field is empty (`amount_text`), so an unflushed grouped value is not overwritten.
- First paint of empty lists uses **skeleton rows**, not a blank flash. Hidden-tab reloads stay coalesced (`ReloadGate` + `AppState.notify(coalesce=True)`).
- Формы / lock: `clamp_content_width` вместо жёстких `width=280/340`.
- Графики: `chart_layout` / `compact_chart_size` от `layout_width`.
- ПК и мобильные: одна floating bottom nav (sidebar нет — паритет полный); на lg/xl nav сгруппирован (~520–560 px), вкладки не расползаются на всю ширину окна.
- Resize: смена breakpoint пересобирает кэш страниц, чтобы сетки и gutters совпали с новым окном.
- **Safe area:** `wrap_safe_area` (Flutter `SafeArea`) on the app shell, lock, splash, fullscreen forms/pickers, attachment viewer, and toasts. Uses MediaQuery padding (notch / Dynamic Island / home indicator / landscape sides) plus a small floor (`SAFE_MIN_TOP/BOTTOM` 8/4) — not a per-device pixel map. Nested lock SafeArea uses `minimum=0` so the floor is not doubled. List `LIST_NAV_CLEARANCE` only clears the floating nav; the home indicator is SafeArea. `maintain_bottom_view_padding` keeps the bottom inset when the keyboard is up.

---

## 10. Связанные документы

- Bootstrap и слои — [ARCHITECTURE.md](ARCHITECTURE.md)  
- Сервисы — [INFRASTRUCTURE.md](INFRASTRUCTURE.md)  
- Сценарии — [USE_CASES.md](USE_CASES.md)  
