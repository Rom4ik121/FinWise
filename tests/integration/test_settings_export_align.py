"""Settings, export, align, and data wipe."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from lib.domain.entities.settings import AppSettings
from lib.domain.use_cases.align_currencies import align_sole_account_currency
from lib.infrastructure.services.data_reset_service import DataResetService
from lib.infrastructure.services.export_service import ExportService
from tests.conftest import run_async
from tests.factories import make_account, make_transaction


def test_settings_language_and_theme(container) -> None:
    async def _run() -> None:
        settings = await container.get_settings.execute()
        settings.language = "uz"
        settings.theme = "light"
        settings.default_currency = "UZS"
        saved = await container.update_settings.execute(settings)
        assert saved.language == "uz"
        assert saved.theme == "light"
        assert saved.default_currency == "UZS"
        assert saved.language_user_set is False

        settings.language = "de"
        settings.language_user_set = True
        saved = await container.update_settings.execute(settings)
        assert saved.language == "de"
        assert saved.language_user_set is True

        settings.ui_style = "neon"
        saved = await container.update_settings.execute(settings)
        assert saved.ui_style == "neon"

        settings.ui_style = "classic"
        saved = await container.update_settings.execute(settings)
        assert saved.ui_style == "classic"

    run_async(_run())


def test_clear_pin_disables_biometric(container) -> None:
    async def _run() -> None:
        repo = container.settings_repository
        await repo.set_pin_credentials("hash", "salt", biometric_enabled=True)
        pin_hash, pin_salt, biometric = await repo.get_pin_credentials()
        assert pin_hash and pin_salt and biometric is True

        await repo.clear_pin_credentials()
        pin_hash, pin_salt, biometric = await repo.get_pin_credentials()
        assert pin_hash is None
        assert pin_salt is None
        assert biometric is False

        settings = await container.get_settings.execute()
        assert settings.biometric_enabled is False

    run_async(_run())


def test_container_rebind_session_factory_after_reset(container) -> None:
    from lib.core.database import get_session_factory, reset_engine

    old = container.settings_repository._session_factory
    reset_engine()
    factory = get_session_factory(container.config)
    container.rebind_session_factory(factory)
    assert container.settings_repository._session_factory is factory
    assert container.settings_repository._session_factory is not old

    async def _run() -> None:
        settings = await container.get_settings.execute()
        assert settings.id == "default"

    run_async(_run())


def test_export_data_use_case(container, tmp_path: Path) -> None:
    async def _run() -> None:
        from lib.domain.entities.category import CategoryKind
        from tests.factories import make_category

        await container.create_account.execute(make_account(name="Cash"))
        await container.create_category.execute(
            make_category(name="Food", kind=CategoryKind.EXPENSE)
        )
        from datetime import datetime, timezone
        from decimal import Decimal

        now = datetime.now(timezone.utc)
        await container.set_budget.execute("Food", now.month, now.year, Decimal("100"))
        result = await container.export_data.execute(tmp_path / "exports")
        assert result.path.exists()
        payload = json.loads(result.path.read_text(encoding="utf-8"))
        assert result.counts["accounts"] >= 1
        assert result.counts["categories"] >= 1
        assert result.counts["budgets"] >= 1
        assert "accounts" in payload
        assert "categories" in payload
        assert "budgets" in payload
        assert payload["version"] >= 2
        assert "debt_payments" in payload or payload["version"] == 2
        settings = payload.get("settings") or {}
        assert "pin_hash" not in settings
        assert "pin_salt" not in settings

    run_async(_run())


def test_export_data_rejects_path_escape(container, tmp_path: Path) -> None:
    async def _run() -> None:
        export_dir = tmp_path / "exports"
        result = await container.export_data.execute(
            export_dir, filename="../../escaped.json"
        )
        assert result.path.parent.resolve() == export_dir.resolve()
        assert result.path.name == "escaped.json"
        assert result.path.is_file()
        outside = tmp_path / "escaped.json"
        assert not outside.exists()

    run_async(_run())


def test_export_configured_pdf_filters_accounts(container, tmp_path: Path) -> None:
    from datetime import datetime, timezone

    from lib.presentation.pdf_export import export_configured_pdf
    from lib.presentation.widgets.pdf_export_sheet import PdfExportChoice
    from lib.infrastructure.services.export_service import PdfSectionFlags

    async def _run() -> None:
        personal = await container.create_account.execute(
            make_account(name="Cash", currency="UZS")
        )
        await container.create_account.execute(
            make_account(name="CorpDesk", currency="UZS", is_corporate=True)
        )
        now = datetime.now(timezone.utc)
        await container.add_transaction.execute(
            make_transaction(personal.id, amount="25", currency="UZS")
        )
        choice = PdfExportChoice(
            period_key="30d",
            date_from=now.replace(day=1) if now.day > 1 else now,
            date_to=now,
            period_label="30 дней",
            account_scope="personal",
            account_ids=frozenset({personal.id}),
            sections=PdfSectionFlags(
                summary=True,
                accounts=True,
                transactions=True,
                categories=True,
                charts=False,
                goals=False,
                debts=False,
                subscriptions=False,
            ),
        )
        path = await export_configured_pdf(container, choice, language="ru")
        assert path.is_file()
        assert path.stat().st_size > 500

    run_async(_run())


def test_export_service_json_csv(tmp_path: Path) -> None:
    from lib.core.config import AppConfig

    cfg = AppConfig(data_dir=tmp_path)
    cfg.ensure_directories()
    svc = ExportService(cfg)
    json_path = svc.export_json({"accounts": [], "transactions": []})
    assert json_path.exists()
    csv_path = svc.export_transactions_csv([])
    assert csv_path.exists()


def test_align_sole_account_currency(container) -> None:
    async def _run() -> None:
        from datetime import datetime, timezone
        from decimal import Decimal

        from lib.domain.entities.currency import ExchangeRate

        await container.currency_repository.upsert_rate(
            ExchangeRate(
                base="RUB",
                quote="UZS",
                rate=Decimal("150"),
                updated_at=datetime.now(timezone.utc),
            )
        )
        acc = await container.create_account.execute(
            make_account(currency="RUB", balance="100")
        )
        await container.add_transaction.execute(
            make_transaction(acc.id, amount="10", currency="RUB")
        )
        settings = await container.get_settings.execute()
        settings.default_currency = "UZS"
        await container.update_settings.execute(settings)

        changed = await align_sole_account_currency(container)
        assert changed is True
        updated = await container.account_repository.get_by_id(acc.id)
        assert updated is not None
        assert updated.currency == "UZS"
        assert updated.initial_balance == Decimal("15000.00")
        txs = await container.list_transactions.execute(account_id=acc.id)
        assert all(t.currency == "UZS" for t in txs)
        assert all(t.amount == Decimal("1500.00") for t in txs)

        # Second call is a no-op.
        assert await align_sole_account_currency(container) is False

    run_async(_run())


def test_align_sole_account_converts_line_items(container) -> None:
    """Line items must convert with the parent amount (#116)."""

    async def _run() -> None:
        from datetime import datetime, timezone
        from decimal import Decimal

        from lib.domain.entities.currency import ExchangeRate
        from lib.domain.entities.transaction import TransactionItem

        await container.currency_repository.upsert_rate(
            ExchangeRate(
                base="RUB",
                quote="UZS",
                rate=Decimal("100"),
                updated_at=datetime.now(timezone.utc),
            )
        )
        acc = await container.create_account.execute(
            make_account(currency="RUB", balance="100")
        )
        await container.add_transaction.execute(
            make_transaction(acc.id, amount="10", currency="RUB").model_copy(
                update={
                    "items": [
                        TransactionItem(
                            name="A", amount=Decimal("4"), category="Еда"
                        ),
                        TransactionItem(
                            name="B", amount=Decimal("6"), category="Еда"
                        ),
                    ]
                }
            )
        )
        settings = await container.get_settings.execute()
        settings.default_currency = "UZS"
        await container.update_settings.execute(settings)

        assert await align_sole_account_currency(container) is True
        txs = await container.list_transactions.execute(account_id=acc.id)
        assert len(txs) == 1
        assert txs[0].amount == Decimal("1000.00")
        assert [i.amount for i in txs[0].items] == [
            Decimal("400.00"),
            Decimal("600.00"),
        ]

    run_async(_run())


def test_align_sole_account_refuses_without_rate(container) -> None:
    async def _run() -> None:
        await container.create_account.execute(
            make_account(currency="EUR", balance="100")
        )
        settings = await container.get_settings.execute()
        settings.default_currency = "UZS"
        await container.update_settings.execute(settings)
        assert await align_sole_account_currency(container) is False
        accounts = await container.list_accounts.execute(active_only=False)
        assert accounts[0].currency == "EUR"

    run_async(_run())


def test_data_reset_wipes_accounts(container) -> None:
    from lib.core.database import get_session_factory

    async def _run() -> None:
        await container.create_account.execute(make_account())
        assert await container.list_accounts.execute()
        media = container.config.media_dir / "receipts" / "tx-wipe"
        media.mkdir(parents=True, exist_ok=True)
        (media / "shot.jpg").write_bytes(b"\xff\xd8\xff")
        DataResetService(container.config).wipe_all(
            get_session_factory(container.config)
        )
        assert await container.list_accounts.execute() == []
        assert not (container.config.media_dir / "receipts" / "tx-wipe").exists()

    run_async(_run())


def test_persist_dashboard_chart_prefs(container) -> None:
    async def _run() -> None:
        settings = await container.get_settings.execute()
        updated = settings.model_copy(
            update={"dashboard_hide_chart": True, "dashboard_chart_days": 90}
        )
        saved = await container.update_settings.execute(updated)
        assert saved.dashboard_hide_chart is True
        assert saved.dashboard_chart_days == 90
        again = await container.get_settings.execute()
        assert again.dashboard_hide_chart is True
        assert again.dashboard_chart_days == 90

    run_async(_run())
