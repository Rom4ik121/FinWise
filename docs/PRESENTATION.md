# Презентация (Flet)

## Оболочка (`app.py`)

`FinanseApp`: четыре вкладки (Главная, Операции, Счета, Настройки),
`AnimatedSwitcher`, кэш страниц, LockScreen если задан PIN. После разблокировки
срабатывает отложенный голосовой захват (`pending_voice_capture`).

Вторичные маршруты состояния (не URL): `analytics`, `account:{id}`, `goals`,
`debts`, `subscriptions`, `currencies`, `budgets`.

Deep link ОС: `finwise://voice` → `voice_shortcut.install_voice_shortcut`.

## Состояние (`state/app_state.py`)

Observer: `subscribe` / `notify` (с coalesce). `bump_refresh(*scopes)`.
Навигация: `set_tab`, `open_secondary`, `close_secondary`.
`ui_style`, язык, валюта, lock, `pending_voice_capture`.

## Скины (`skins/`)

`classic` — светлая/тёмная системная тема.  
`neon` — тёмно-серый градиент, стекло (`glass_layer` + Blur), акценты.
Выбор в настройках (`settings.ui_style`).

## Страницы

| Страница | Содержание |
|---|---|
| dashboard | Баланс, быстрые действия, бюджеты, бейджи |
| transactions | Поиск, фильтры, группировка, CRUD, перевод |
| accounts / account_detail | Счета, статистика, графики счёта |
| analytics | Один поток: категории дохода и расхода + линия за полный период (пустые дни — нули) |
| goals / debts / subscriptions / budgets / currencies | Профили сущностей |
| settings | Тема, скин, язык, валюта, пуши, PIN/биометрия, голос, экспорт, бэкап, сброс |

## Виджеты

Карточки счетов/операций/целей/долгов/подписок, QuickAdd (в т.ч. микрофон),
TransferSheet, CategoryPicker, CurrencyTickerPicker, DateTimeField,
LockScreen, Splash, Charts (центрированный пончик, линия с заполнением периода),
DualAddButton, ConfirmDialog, FullscreenForm.

## Файлы (`file_transfer.py`)

`offer_saved_file`: `save_file(..., src_bytes=...)`, затем
`materialize_saved_file` (реальная копия). Отмена → `None`, без фейкового
успеха. Телефон: share sheet. Restore: `pick_files(with_data=True)`,
классификация sqlite/json.

## Голос (`voice_shortcut.py`)

Маршрут `finwise://voice` или `/voice`. Пока приложение открыто, плагин речи
может поднять `on_voice_request` (в т.ч. долгое зажатие громкости вниз).
Фраза: «расход такси 500» / «доход зарплата 2 млн».

## Утилиты

`format_money` / compact, `run_async`, `snack`, `tr`, кэш RateBook,
`convert_currency_safe`. Тема: `theme.py`, стекло и карточки: `styles.py`.
Иконки: `icon_registry.py`, валютные глифы: `account_icons.py`.
Ввод сумм: `money_input.py`. Периоды аналитики: `analytics_period.py`
(`enumerate_period_keys`, `fill_time_series`).
