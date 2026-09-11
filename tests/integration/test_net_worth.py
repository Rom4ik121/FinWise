"""Daily net-worth snapshots for analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tests.conftest import run_async
from tests.factories import make_account, make_transaction


def test_net_worth_snapshot_upsert_and_window(container) -> None:
    async def _run() -> None:
        acc = await container.create_account.execute(make_account(balance="1000"))
        first = await container.record_net_worth_snapshot.execute()
        assert first.amount == Decimal("1000.00")
        again = await container.record_net_worth_snapshot.execute()
        assert again.captured_on == first.captured_on
        assert again.amount == Decimal("1000.00")

        await container.add_transaction.execute(
            make_transaction(acc.id, amount="100")
        )
        updated = await container.record_net_worth_snapshot.execute()
        assert updated.captured_on == first.captured_on
        assert updated.amount == Decimal("900.00")

        yesterday = datetime.now(timezone.utc) - timedelta(days=2)
        older = await container.record_net_worth_snapshot.execute(as_of=yesterday)
        assert older.captured_on == yesterday.date()

        window = await container.list_net_worth_snapshots.execute(
            date_from=yesterday.date()
        )
        assert len(window) >= 2
        assert window[0].captured_on <= window[-1].captured_on
        listed_all = await container.list_net_worth_snapshots.execute()
        assert any(s.captured_on == first.captured_on for s in listed_all)

    run_async(_run())
