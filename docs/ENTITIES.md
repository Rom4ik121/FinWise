# Доменные сущности

Pydantic v2, `from_attributes=True`. Деньги — `quantize_money` (2 знака).
Даты — UTC.

## Account

Счёт: `name`, `currency`, `balance`, `initial_balance`, `icon`, `color`,
`is_active`. Баланс = начальный + доходы − расходы (включая переводы).

## Transaction

`amount > 0`, `type` income|expense, `category` (имя), теги, связи
`goal_id` / `debt_id` / `subscription_id`, для FX-целей/долгов —
`goal_credit_amount` / `debt_credit_amount`.  
Перевод: общий `transfer_id` и `transfer_peer_account_id`.  
`is_transfer` — есть `transfer_id`. Сумму перевода через update менять нельзя.

## Category

Уникальное `name`, `kind` income|expense|both, иконка/цвет.  
`matches_type(tx_type)` — подходит ли категория типу операции.

## Currency / ExchangeRate

Код ISO, имена, символ, `is_crypto`. Курс `base`→`quote`, Numeric(24,12).

## Goal

`target_amount` / `current_amount`, валюта, дедлайн, приоритет 1–5,
`status` active|completed|archived, кэш проекции JSON.

## Debt

Контрагент, `amount` / `remaining_amount`, `direction` i_owe|owed_to_me,
`status` active|overdue|paid|archived, `interest_rate` % годовых, `due_date`.

## Subscription

Сумма, счёт, категория, `periodicity` (+ `custom_interval_days`),
`next_billing_date`, `auto_charge`, лимиты платежей и дат, `status`.

## Budget / BudgetProgress

Лимит категории на месяц/год, `spent`, `last_alert_level`. Progress —
доля и флаги порогов.

## AppSettings

`default_currency`, `theme` light|dark, `ui_style` classic|neon, `language`
ru|en|uz, интервал курсов, флаги уведомлений, `reminder_time` (HH:MM),
`reminder_days`, `budget_alerts`, `check_balance_before_subscription`,
PIN hash/salt, `biometric_enabled`.

## Money

`quantize_money` — 2 знака. `quantize_rate` — мелкие курсы (UZS и крипто).
