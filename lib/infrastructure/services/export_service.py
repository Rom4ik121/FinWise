"""Export finances to JSON, CSV, and PDF summary reports."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from lib.core.config import AppConfig, get_default_config
from lib.domain.entities.account import Account
from lib.domain.entities.debt import Debt
from lib.domain.entities.goal import Goal
from lib.domain.entities.money import quantize_money
from lib.domain.entities.subscription import Subscription
from lib.domain.entities.transaction import Transaction

logger = logging.getLogger("finanse.infrastructure.services.export")


def _account_pdf_strings(lang: str) -> dict[str, str]:
    """Localized labels for account period PDF (ru / en / uz)."""
    packs = {
        "ru": {
            "title": "Отчёт по счёту",
            "generated": "Сформирован",
            "summary": "Сводка",
            "balance": "Баланс",
            "income": "Доход",
            "expense": "Расход",
            "net": "Итог",
            "of_turnover": "от оборота",
            "tx_count": "Операций расхода за период",
            "by_category": "Расходы по категориям",
            "expenses": "Операции расхода",
            "dynamics": "Динамика",
            "empty": "Нет данных за период",
            "col_date": "Дата",
            "col_category": "Категория",
            "col_amount": "Сумма",
            "col_share": "Доля",
            "income_short": "Доход",
            "expense_short": "Расход",
            "footer_hint": "Локальный отчёт FinWise",
        },
        "en": {
            "title": "Account report",
            "generated": "Generated",
            "summary": "Summary",
            "balance": "Balance",
            "income": "Income",
            "expense": "Expense",
            "net": "Net",
            "of_turnover": "of turnover",
            "tx_count": "Expense transactions in period",
            "by_category": "Spending by category",
            "expenses": "Expense transactions",
            "dynamics": "Dynamics",
            "empty": "No data for this period",
            "col_date": "Date",
            "col_category": "Category",
            "col_amount": "Amount",
            "col_share": "Share",
            "income_short": "Income",
            "expense_short": "Expense",
            "footer_hint": "FinWise local report",
        },
        "uz": {
            "title": "Hisob hisoboti",
            "generated": "Yaratilgan",
            "summary": "Xulosa",
            "balance": "Balans",
            "income": "Daromad",
            "expense": "Xarajat",
            "net": "Natija",
            "of_turnover": "aylanmadan",
            "tx_count": "Davrdagi xarajat amaliyotlari",
            "by_category": "Toifalar bo‘yicha xarajat",
            "expenses": "Xarajat amaliyotlari",
            "dynamics": "Dinamika",
            "empty": "Bu davr uchun ma’lumot yo‘q",
            "col_date": "Sana",
            "col_category": "Toifa",
            "col_amount": "Summa",
            "col_share": "Ulush",
            "income_short": "Daromad",
            "expense_short": "Xarajat",
            "footer_hint": "FinWise mahalliy hisobot",
        },
    }
    return packs.get(lang, packs["en"])


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


class ExportService:
    """Serialize domain data to JSON / CSV / PDF under the export directory."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self._config = config or get_default_config()
        self._config.ensure_directories()

    @property
    def export_dir(self) -> Path:
        return self._config.export_dir

    def export_json(
        self,
        data: dict[str, Any] | Sequence[Any],
        filename: str = "export.json",
    ) -> Path:
        """Write ``data`` as pretty JSON and return the file path."""
        path = self._resolve(filename)
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=_json_default),
                encoding="utf-8",
            )
            logger.info("Exported JSON to %s", path)
            return path
        except OSError:
            logger.exception("Failed to write JSON export %s", path)
            raise

    def export_transactions_csv(
        self,
        transactions: Iterable[Transaction],
        filename: str = "transactions.csv",
    ) -> Path:
        """Export transactions to CSV."""
        path = self._resolve(filename)
        fieldnames = [
            "id",
            "account_id",
            "amount",
            "category",
            "tags",
            "date",
            "comment",
            "type",
            "currency",
            "goal_id",
            "debt_id",
            "created_at",
            "updated_at",
        ]
        try:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for tx in transactions:
                    writer.writerow(
                        {
                            "id": tx.id,
                            "account_id": tx.account_id,
                            "amount": str(tx.amount),
                            "category": tx.category,
                            "tags": "|".join(tx.tags),
                            "date": tx.date.isoformat(),
                            "comment": tx.comment,
                            "type": tx.type.value if hasattr(tx.type, "value") else tx.type,
                            "currency": tx.currency,
                            "goal_id": tx.goal_id or "",
                            "debt_id": getattr(tx, "debt_id", None) or "",
                            "created_at": tx.created_at.isoformat(),
                            "updated_at": tx.updated_at.isoformat(),
                        }
                    )
            logger.info("Exported transactions CSV to %s", path)
            return path
        except OSError:
            logger.exception("Failed to write CSV export %s", path)
            raise

    def export_full_json(
        self,
        *,
        accounts: Sequence[Account] = (),
        transactions: Sequence[Transaction] = (),
        goals: Sequence[Goal] = (),
        debts: Sequence[Debt] = (),
        subscriptions: Sequence[Subscription] = (),
        filename: str = "finanse_backup_data.json",
    ) -> Path:
        """Export a structured JSON dump of core entities."""
        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "accounts": [a.model_dump(mode="json") for a in accounts],
            "transactions": [t.model_dump(mode="json") for t in transactions],
            "goals": [g.model_dump(mode="json") for g in goals],
            "debts": [d.model_dump(mode="json") for d in debts],
            "subscriptions": [s.model_dump(mode="json") for s in subscriptions],
        }
        return self.export_json(payload, filename=filename)

    def export_summary_pdf(
        self,
        *,
        accounts: Sequence[Account] = (),
        transactions: Sequence[Transaction] = (),
        goals: Sequence[Goal] = (),
        debts: Sequence[Debt] = (),
        subscriptions: Sequence[Subscription] = (),
        filename: str = "summary_report.pdf",
        title: str = "FinWise Summary Report",
    ) -> Path:
        """Generate a simple PDF summary using reportlab."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm
            from reportlab.pdfgen import canvas
        except ImportError as exc:
            logger.error("reportlab is required for PDF export")
            raise RuntimeError(
                "reportlab is not installed; add it to dependencies for PDF export"
            ) from exc

        path = self._resolve(filename)
        income = sum(
            (t.amount for t in transactions if str(getattr(t.type, "value", t.type)) == "income"),
            Decimal("0"),
        )
        expense = sum(
            (t.amount for t in transactions if str(getattr(t.type, "value", t.type)) == "expense"),
            Decimal("0"),
        )
        total_balance = sum((a.balance for a in accounts), Decimal("0"))
        active_debts = [d for d in debts if str(getattr(d.status, "value", d.status)) == "active"]
        debt_remaining = sum((d.remaining_amount for d in active_debts), Decimal("0"))
        active_subs = [s for s in subscriptions if s.is_active]
        open_goals = [g for g in goals if not g.is_completed]

        try:
            c = canvas.Canvas(str(path), pagesize=A4)
            width, height = A4
            y = height - 2 * cm

            c.setFont("Helvetica-Bold", 16)
            c.drawString(2 * cm, y, title)
            y -= 1 * cm
            c.setFont("Helvetica", 10)
            c.drawString(
                2 * cm,
                y,
                f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            )
            y -= 1.2 * cm

            lines = [
                f"Accounts: {len(accounts)}  |  Total balance: {total_balance}",
                f"Transactions: {len(transactions)}  |  Income: {income}  |  Expense: {expense}",
                f"Net (income - expense): {income - expense}",
                f"Active goals: {len(open_goals)} / {len(goals)}",
                f"Active debts: {len(active_debts)}  |  Remaining: {debt_remaining}",
                f"Active subscriptions: {len(active_subs)}",
            ]
            c.setFont("Helvetica", 11)
            for line in lines:
                c.drawString(2 * cm, y, line)
                y -= 0.7 * cm

            y -= 0.5 * cm
            c.setFont("Helvetica-Bold", 12)
            c.drawString(2 * cm, y, "Accounts")
            y -= 0.6 * cm
            c.setFont("Helvetica", 10)
            for account in accounts[:20]:
                if y < 2 * cm:
                    c.showPage()
                    y = height - 2 * cm
                    c.setFont("Helvetica", 10)
                c.drawString(
                    2 * cm,
                    y,
                    f"- {account.name}: {account.balance} {account.currency}",
                )
                y -= 0.5 * cm

            if open_goals:
                y -= 0.4 * cm
                c.setFont("Helvetica-Bold", 12)
                c.drawString(2 * cm, y, "Goals")
                y -= 0.6 * cm
                c.setFont("Helvetica", 10)
                for goal in open_goals[:15]:
                    if y < 2 * cm:
                        c.showPage()
                        y = height - 2 * cm
                        c.setFont("Helvetica", 10)
                    ratio = goal.progress_ratio
                    c.drawString(
                        2 * cm,
                        y,
                        f"- {goal.name}: {goal.current_amount}/{goal.target_amount} ({ratio:.0%})",
                    )
                    y -= 0.5 * cm

            c.save()
            logger.info("Exported PDF summary to %s", path)
            return path
        except Exception:
            logger.exception("Failed to write PDF export %s", path)
            raise

    def export_account_period_pdf(
        self,
        *,
        account_name: str,
        currency: str,
        period_label: str,
        balance: Decimal,
        income: Decimal,
        expense: Decimal,
        ops_income: Decimal,
        ops_expense: Decimal,
        by_category: Sequence[tuple[str, Decimal]] = (),
        expenses: Sequence[tuple[str, str, Decimal]] = (),
        by_period: Sequence[tuple[str, Decimal, Decimal]] = (),
        filename: str | None = None,
        language: str = "en",
    ) -> Path:
        """PDF report for one account period: KPIs, category %, expenses %, charts."""
        try:
            from reportlab.lib.colors import Color, HexColor, white
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm, mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.pdfgen import canvas
        except ImportError as exc:
            raise RuntimeError(
                "reportlab is not installed; add it to dependencies for PDF export"
            ) from exc

        lang = (language or "en").lower()
        if lang not in ("ru", "en", "uz"):
            lang = "en"
        L = _account_pdf_strings(lang)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in account_name)[
            :40
        ] or "account"
        path = self._resolve(filename or f"account_report_{safe}_{stamp}.pdf")

        font_reg = "Helvetica"
        font_bold = "Helvetica-Bold"
        for candidate in (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/Arial.ttf"),
        ):
            if candidate.is_file():
                try:
                    pdfmetrics.registerFont(TTFont("FinWiseSans", str(candidate)))
                    bold_path = candidate.with_name(
                        candidate.name.replace("Sans", "Sans-Bold").replace(
                            "arial", "arialbd"
                        ).replace("Arial", "arialbd")
                    )
                    if bold_path.is_file():
                        pdfmetrics.registerFont(TTFont("FinWiseSans-Bold", str(bold_path)))
                        font_bold = "FinWiseSans-Bold"
                    else:
                        font_bold = "FinWiseSans"
                    font_reg = "FinWiseSans"
                    break
                except Exception:  # noqa: BLE001
                    pass

        def _money(value: Decimal) -> str:
            return f"{quantize_money(value)} {currency}"

        def _pct(part: Decimal, whole: Decimal) -> str:
            if whole <= 0:
                return "0%"
            return f"{(part / whole * Decimal('100')).quantize(Decimal('0.1'))}%"

        expense_total = (
            quantize_money(ops_expense) if ops_expense > 0 else quantize_money(expense)
        )
        cat_rows = list(by_category)[:12]
        exp_rows = list(expenses)[:40]
        turnover = ops_income + ops_expense
        net = quantize_money(ops_income - ops_expense)
        now_local = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        pie_path = self._render_category_pie_png(cat_rows, expense_total, lang)
        line_path = self._render_cashflow_line_png(list(by_period), lang)

        brand = HexColor("#0F766E")
        brand_dark = HexColor("#115E59")
        surface = HexColor("#F8FAFC")
        ink = HexColor("#0F172A")
        muted = HexColor("#64748B")
        line_color = HexColor("#E2E8F0")
        income_color = HexColor("#0D9488")
        expense_color = HexColor("#E11D48")
        card_fill = HexColor("#FFFFFF")

        try:
            c = canvas.Canvas(str(path), pagesize=A4)
            width, height = A4
            margin = 1.6 * cm
            content_w = width - 2 * margin
            y = height

            def _new_page() -> None:
                nonlocal y
                c.showPage()
                y = height - margin
                _footer()

            def _ensure(space: float) -> None:
                nonlocal y
                if y < margin + space + 1.2 * cm:
                    _new_page()

            def _footer() -> None:
                c.setFillColor(muted)
                c.setFont(font_reg, 8)
                c.drawString(margin, 0.9 * cm, "FinWise")
                c.drawRightString(width - margin, 0.9 * cm, L["footer_hint"])

            def _section_title(text: str) -> None:
                nonlocal y
                _ensure(1.4 * cm)
                y -= 0.35 * cm
                c.setFillColor(brand)
                c.roundRect(margin, y - 0.15 * cm, 3.5 * mm, 0.55 * cm, 1.2, fill=1, stroke=0)
                c.setFillColor(ink)
                c.setFont(font_bold, 12)
                c.drawString(margin + 6 * mm, y, text)
                y -= 0.85 * cm

            def _kpi_card(
                x: float,
                top: float,
                w: float,
                h: float,
                label: str,
                value: str,
                accent: Color,
            ) -> None:
                c.setFillColor(card_fill)
                c.setStrokeColor(line_color)
                c.setLineWidth(0.6)
                c.roundRect(x, top - h, w, h, 6, fill=1, stroke=1)
                c.setFillColor(accent)
                c.rect(x, top - h, 2.2 * mm, h, fill=1, stroke=0)
                c.setFillColor(muted)
                c.setFont(font_reg, 8)
                c.drawString(x + 5 * mm, top - 0.55 * cm, label[:42])
                c.setFillColor(ink)
                c.setFont(font_bold, 10)
                c.drawString(x + 5 * mm, top - 1.15 * cm, value[:36])

            def _bar_row(
                label: str,
                amount: Decimal,
                share: str,
                fraction: float,
                *,
                bar_color: Color = brand,
            ) -> None:
                nonlocal y
                _ensure(0.95 * cm)
                c.setFillColor(ink)
                c.setFont(font_reg, 9)
                c.drawString(margin, y, label[:48])
                c.setFont(font_bold, 9)
                c.drawRightString(width - margin, y, f"{_money(amount)}  ·  {share}")
                y -= 0.38 * cm
                bar_h = 0.22 * cm
                c.setFillColor(HexColor("#EEF2FF"))
                c.roundRect(margin, y, content_w, bar_h, 2, fill=1, stroke=0)
                fill_w = max(0.0, min(1.0, fraction)) * content_w
                if fill_w > 0:
                    c.setFillColor(bar_color)
                    c.roundRect(margin, y, fill_w, bar_h, 2, fill=1, stroke=0)
                y -= 0.55 * cm

            # —— Hero header ——
            header_h = 3.35 * cm
            c.setFillColor(brand_dark)
            c.rect(0, height - header_h, width, header_h, fill=1, stroke=0)
            c.setFillColor(brand)
            c.rect(0, height - header_h, width, 0.18 * cm, fill=1, stroke=0)
            c.setFillColor(white)
            c.setFont(font_bold, 9)
            c.drawString(margin, height - 0.85 * cm, "FINWISE")
            c.setFont(font_bold, 18)
            c.drawString(margin, height - 1.65 * cm, f"{L['title']}: {account_name}"[:70])
            c.setFont(font_reg, 10)
            c.drawString(margin, height - 2.35 * cm, period_label[:60])
            c.setFont(font_reg, 8)
            c.drawString(margin, height - 2.95 * cm, f"{L['generated']}: {now_local}")
            y = height - header_h - 0.7 * cm
            _footer()

            # —— KPI cards ——
            _section_title(L["summary"])
            card_h = 1.55 * cm
            gap = 0.28 * cm
            card_w = (content_w - gap) / 2
            _kpi_card(margin, y, card_w, card_h, L["balance"], _money(balance), brand)
            _kpi_card(
                margin + card_w + gap,
                y,
                card_w,
                card_h,
                L["net"],
                _money(net),
                income_color if net >= 0 else expense_color,
            )
            y -= card_h + gap
            _kpi_card(
                margin,
                y,
                card_w,
                card_h,
                L["income"],
                _money(ops_income),
                income_color,
            )
            exp_share = _pct(ops_expense, turnover)
            _kpi_card(
                margin + card_w + gap,
                y,
                card_w,
                card_h,
                f"{L['expense']} ({exp_share} {L['of_turnover']})",
                _money(ops_expense),
                expense_color,
            )
            y -= card_h + 0.45 * cm
            c.setFillColor(muted)
            c.setFont(font_reg, 9)
            c.drawString(
                margin,
                y,
                f"{L['tx_count']}: {len(exp_rows) if exp_rows else '—'}",
            )
            y -= 0.55 * cm

            # —— Categories ——
            _section_title(L["by_category"])
            if pie_path and pie_path.is_file():
                pie_h = 7.0 * cm
                _ensure(pie_h + 0.4 * cm)
                c.drawImage(
                    str(pie_path),
                    margin + 0.4 * cm,
                    y - pie_h,
                    width=content_w - 0.8 * cm,
                    height=pie_h,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                y -= pie_h + 0.35 * cm

            if not cat_rows:
                c.setFillColor(muted)
                c.setFont(font_reg, 9)
                c.drawString(margin, y, L["empty"])
                y -= 0.5 * cm
            else:
                for cat, amount in cat_rows:
                    share = _pct(amount, expense_total)
                    frac = float(amount / expense_total) if expense_total > 0 else 0.0
                    _bar_row(cat, amount, share, frac)

            # —— Expense ops ——
            _section_title(L["expenses"])
            if not exp_rows:
                c.setFillColor(muted)
                c.setFont(font_reg, 9)
                c.drawString(margin, y, L["empty"])
                y -= 0.5 * cm
            else:
                # Table header
                _ensure(0.7 * cm)
                c.setFillColor(surface)
                c.roundRect(margin, y - 0.35 * cm, content_w, 0.55 * cm, 3, fill=1, stroke=0)
                c.setFillColor(muted)
                c.setFont(font_bold, 8)
                c.drawString(margin + 3 * mm, y - 0.15 * cm, L["col_date"])
                c.drawString(margin + 3.4 * cm, y - 0.15 * cm, L["col_category"])
                c.drawRightString(width - margin - 2.8 * cm, y - 0.15 * cm, L["col_amount"])
                c.drawRightString(width - margin - 2 * mm, y - 0.15 * cm, L["col_share"])
                y -= 0.7 * cm
                for i, (when, category, amount) in enumerate(exp_rows):
                    _ensure(0.55 * cm)
                    if i % 2 == 0:
                        c.setFillColor(HexColor("#F1F5F9"))
                        c.rect(margin, y - 0.18 * cm, content_w, 0.48 * cm, fill=1, stroke=0)
                    share = _pct(amount, expense_total)
                    c.setFillColor(ink)
                    c.setFont(font_reg, 8)
                    c.drawString(margin + 3 * mm, y, when[:16])
                    c.drawString(margin + 3.4 * cm, y, category[:28])
                    c.setFont(font_bold, 8)
                    c.drawRightString(width - margin - 2.8 * cm, y, _money(amount)[:22])
                    c.setFillColor(muted)
                    c.setFont(font_reg, 8)
                    c.drawRightString(width - margin - 2 * mm, y, share)
                    y -= 0.5 * cm

            # —— Dynamics ——
            if line_path and line_path.is_file():
                _section_title(L["dynamics"])
                line_h = 6.8 * cm
                _ensure(line_h + 0.3 * cm)
                c.drawImage(
                    str(line_path),
                    margin,
                    y - line_h,
                    width=content_w,
                    height=line_h,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                y -= line_h + 0.3 * cm

            c.save()
            logger.info("Exported account period PDF to %s", path)
            return path
        finally:
            for tmp in (pie_path, line_path):
                if tmp is not None:
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        pass

    def _render_category_pie_png(
        self,
        rows: Sequence[tuple[str, Decimal]],
        total: Decimal,
        language: str,
    ) -> Path | None:
        if not rows or total <= 0:
            return None
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return None
        labels = [name[:20] for name, _ in rows]
        sizes = [float(amt) for _name, amt in rows]
        palette = [
            "#0D9488",
            "#2563EB",
            "#F59E0B",
            "#E11D48",
            "#8B5CF6",
            "#14B8A6",
            "#F97316",
            "#64748B",
            "#06B6D4",
            "#84CC16",
            "#EC4899",
            "#A855F7",
        ]
        colors = [palette[i % len(palette)] for i in range(len(sizes))]
        path = self.export_dir / f"_tmp_pie_{datetime.now(timezone.utc).timestamp()}.png"
        fig, ax = plt.subplots(figsize=(6.2, 4.4), facecolor="white")
        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=None,
            autopct="%1.1f%%",
            startangle=90,
            colors=colors,
            pctdistance=0.72,
            wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
            textprops={"fontsize": 8, "color": "#0F172A"},
        )
        for t in autotexts:
            t.set_fontsize(8)
            t.set_fontweight("bold")
        ax.legend(
            wedges,
            labels,
            loc="center left",
            bbox_to_anchor=(1.0, 0.5),
            fontsize=8,
            frameon=False,
        )
        ax.axis("equal")
        fig.tight_layout()
        fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return path

    def _render_cashflow_line_png(
        self,
        series: Sequence[tuple[str, Decimal, Decimal]],
        language: str,
    ) -> Path | None:
        if len(series) < 2:
            return None
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return None
        L = _account_pdf_strings((language or "en").lower())
        labels = [p[0][-5:] if len(p[0]) >= 5 else p[0] for p in series]
        income = [float(p[1]) for p in series]
        expense = [float(p[2]) for p in series]
        path = self.export_dir / f"_tmp_line_{datetime.now(timezone.utc).timestamp()}.png"
        fig, ax = plt.subplots(figsize=(7.4, 3.5), facecolor="white")
        ax.plot(labels, income, label=L["income_short"], color="#0D9488", linewidth=2.2)
        ax.plot(labels, expense, label=L["expense_short"], color="#E11D48", linewidth=2.2)
        ax.fill_between(range(len(labels)), income, alpha=0.12, color="#0D9488")
        ax.fill_between(range(len(labels)), expense, alpha=0.12, color="#E11D48")
        ax.legend(fontsize=8, frameon=False)
        ax.set_facecolor("#F8FAFC")
        ax.grid(True, axis="y", color="#E2E8F0", linewidth=0.8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="x", labelrotation=45, labelsize=7)
        ax.tick_params(axis="y", labelsize=8)
        fig.tight_layout()
        fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return path

    def _resolve(self, filename: str) -> Path:
        path = Path(filename)
        if not path.is_absolute():
            path = self.export_dir / path.name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
