"""Stage 1 Sales proactive detectors, dedup logging, and Desk/Telegram routing."""

from __future__ import annotations

from datetime import date, datetime

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, nowdate

from aios_v1.lib.connector import notify, telegram_client
from aios_v1.lib.draft_manager import _format_currency_amount
from aios_v1.lib.error_utils import log_exception

HEARTBEAT_TIMEOUT_SECONDS = 300
SALES_BRANCH = "sales"
INSIGHT_LOG_DOCTYPE = "AIOS Proactive Insight Log"

# Thresholds locked by Ten for Stage 1
QUOTATION_SOON_DAYS = 3
QUOTATION_EXPIRED_GRACE_DAYS = 7
SO_WARNING_DAYS = 2
SO_OVERDUE_MIN_DAYS = 1
DN_UNBILLED_MIN_AGE_DAYS = 3


def _resolve_company(company: str | None = None) -> str:
    if company and company.strip():
        return company.strip()
    comp = (
        frappe.defaults.get_global_default("company")
        or frappe.db.get_single_value("AIOS Setting", "default_company")
        or frappe.db.get_value("Company", {}, "name")
    )
    if not comp:
        frappe.throw("Company aktif belum dikonfigurasi untuk pemindaian proaktif Sales.")
    return str(comp)


def _is_demo_row(row: dict) -> bool:
    for key in ("customer_name", "customer", "party_name", "name"):
        val = str(row.get(key) or "").upper()
        if "DEMO" in val:
            return True
    return False


def _sort_findings(findings: list[dict], date_key: str) -> list[dict]:
    return sorted(
        findings,
        key=lambda item: (
            -float(item.get("base_grand_total") or 0.0),
            getdate(item.get(date_key) or nowdate()),
            str(item.get("name") or ""),
        ),
    )


def _sort_findings_by_value(findings: list[dict]) -> list[dict]:
    """Urut nilai terbesar lebih dulu; dipakai temuan yang tidak punya tanggal acuan."""
    return sorted(
        findings,
        key=lambda item: (-float(item.get("base_grand_total") or 0.0), str(item.get("name") or "")),
    )


def evaluate_quotation_rows(rows: list[dict], today: date | None = None) -> list[dict]:
    """Evaluate Quotation rows: H-3..H+0 expiring soon and H+1..H+7 recently expired."""
    ref_today = getdate(today or nowdate())
    findings: list[dict] = []
    allowed_statuses = {"Open", "Replied", "Partially Ordered"}

    for row in rows:
        if int(row.get("docstatus") or 0) != 1:
            continue
        if str(row.get("status") or "") not in allowed_statuses:
            continue
        if row.get("has_sales_order"):
            continue
        valid_till_raw = row.get("valid_till")
        if not valid_till_raw:
            continue
        valid_till = getdate(valid_till_raw)
        delta_days = (valid_till - ref_today).days

        if 0 <= delta_days <= QUOTATION_SOON_DAYS:
            severity = "expiring_soon"
            label = f"berlaku {delta_days} hari lagi ({valid_till})" if delta_days > 0 else f"berakhir hari ini ({valid_till})"
        elif -QUOTATION_EXPIRED_GRACE_DAYS <= delta_days < 0:
            severity = "expired_recent"
            label = f"kedaluwarsa {abs(delta_days)} hari lalu ({valid_till})"
        else:
            continue

        customer = str(row.get("customer_name") or row.get("party_name") or "-")
        total = float(row.get("base_grand_total") or 0.0)
        is_demo = _is_demo_row(row)
        prefix = "[DEMO] " if is_demo else ""
        findings.append(
            {
                "rule_key": "quotation_followup",
                "reference_doctype": "Quotation",
                "name": str(row.get("name") or ""),
                "customer_name": customer,
                "valid_till": str(valid_till),
                "base_grand_total": total,
                "severity": severity,
                "days_delta": delta_days,
                "is_demo": is_demo,
                "summary": (
                    f"{prefix}Follow-up Penawaran {row.get('name')} ({customer}) — "
                    f"nilai {_format_currency_amount(total)}, {label}."
                ),
            }
        )

    return _sort_findings(findings, "valid_till")


def evaluate_so_rows(rows: list[dict], today: date | None = None) -> list[dict]:
    """Evaluate Sales Order rows: H-2 warning and >=1 day overdue, split partial vs unshipped."""
    ref_today = getdate(today or nowdate())
    findings: list[dict] = []
    allowed_statuses = {"To Deliver and Bill", "To Deliver"}

    for row in rows:
        if int(row.get("docstatus") or 0) != 1:
            continue
        if str(row.get("status") or "") not in allowed_statuses:
            continue
        per_delivered = float(row.get("per_delivered") or 0.0)
        if per_delivered >= 100.0:
            continue
        delivery_raw = row.get("delivery_date")
        if not delivery_raw:
            continue
        delivery_dt = getdate(delivery_raw)
        delta_days = (delivery_dt - ref_today).days

        if delta_days <= -SO_OVERDUE_MIN_DAYS:
            severity = "overdue"
            timing_label = f"terlambat {abs(delta_days)} hari (target {delivery_dt})"
        elif 0 <= delta_days <= SO_WARNING_DAYS:
            severity = "warning"
            timing_label = f"waspada kirim {delta_days} hari lagi ({delivery_dt})" if delta_days > 0 else f"jatuh tempo kirim hari ini ({delivery_dt})"
        else:
            continue

        bucket = "partial" if per_delivered > 0.0 else "unshipped"
        bucket_label = f"terkirim sebagian ({per_delivered:.0f}%)" if bucket == "partial" else "belum kirim sama sekali (0%)"
        customer = str(row.get("customer_name") or row.get("customer") or "-")
        total = float(row.get("base_grand_total") or 0.0)
        is_demo = _is_demo_row(row)
        prefix = "[DEMO] " if is_demo else ""
        findings.append(
            {
                "rule_key": "so_fulfillment",
                "reference_doctype": "Sales Order",
                "name": str(row.get("name") or ""),
                "customer_name": customer,
                "delivery_date": str(delivery_dt),
                "per_delivered": per_delivered,
                "fulfillment_bucket": bucket,
                "base_grand_total": total,
                "severity": severity,
                "days_delta": delta_days,
                "is_demo": is_demo,
                "summary": (
                    f"{prefix}Monitor Pengiriman {row.get('name')} ({customer}) — "
                    f"nilai {_format_currency_amount(total)}, {timing_label}, {bucket_label}."
                ),
            }
        )

    return _sort_findings(findings, "delivery_date")


def evaluate_dn_rows(rows: list[dict], today: date | None = None) -> list[dict]:
    """Evaluate Delivery Note rows: age >= 3 days, per_billed < 100, non-return."""
    ref_today = getdate(today or nowdate())
    findings: list[dict] = []
    allowed_statuses = {"To Bill", "Partially Billed"}

    for row in rows:
        if int(row.get("docstatus") or 0) != 1:
            continue
        if int(row.get("is_return") or 0) == 1:
            continue
        if str(row.get("status") or "") not in allowed_statuses:
            continue
        per_billed = float(row.get("per_billed") or 0.0)
        if per_billed >= 100.0:
            continue
        posting_raw = row.get("posting_date")
        if not posting_raw:
            continue
        posting_dt = getdate(posting_raw)
        age_days = (ref_today - posting_dt).days
        if age_days < DN_UNBILLED_MIN_AGE_DAYS:
            continue

        customer = str(row.get("customer_name") or row.get("customer") or "-")
        total = float(row.get("base_grand_total") or 0.0)
        is_demo = _is_demo_row(row)
        prefix = "[DEMO] " if is_demo else ""
        findings.append(
            {
                "rule_key": "delivered_unbilled",
                "reference_doctype": "Delivery Note",
                "name": str(row.get("name") or ""),
                "customer_name": customer,
                "posting_date": str(posting_dt),
                "per_billed": per_billed,
                "age_days": age_days,
                "base_grand_total": total,
                "severity": "unbilled",
                "is_demo": is_demo,
                "summary": (
                    f"{prefix}Surat Jalan Belum Ditagih {row.get('name')} ({customer}) — "
                    f"nilai {_format_currency_amount(total)}, umur {age_days} hari (tertagih {per_billed:.0f}%)."
                ),
            }
        )

    return _sort_findings(findings, "posting_date")


def scan_quotation_followup(company: str | None = None, today: date | None = None) -> list[dict]:
    """Query live Quotation rows and evaluate follow-up findings."""
    comp = _resolve_company(company)
    ref_today = getdate(today or nowdate())
    min_date = add_days(ref_today, -QUOTATION_EXPIRED_GRACE_DAYS)
    max_date = add_days(ref_today, QUOTATION_SOON_DAYS)

    rows = frappe.get_all(
        "Quotation",
        filters={
            "company": comp,
            "docstatus": 1,
            "status": ["in", ["Open", "Replied", "Partially Ordered"]],
            "valid_till": ["between", [str(min_date), str(max_date)]],
        },
        fields=[
            "name",
            "party_name",
            "customer_name",
            "valid_till",
            "status",
            "docstatus",
            "base_grand_total",
        ],
        limit_page_length=0,
    )
    if not rows:
        return []

    qtn_names = [r["name"] for r in rows]
    linked_rows = frappe.db.sql(
        """
        SELECT DISTINCT soi.prevdoc_docname
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 1
          AND soi.prevdoc_docname IN %(names)s
        """,
        {"names": qtn_names},
        as_dict=True,
    )
    linked_set = {r.prevdoc_docname for r in linked_rows if r.prevdoc_docname}
    for r in rows:
        r["has_sales_order"] = r["name"] in linked_set

    return evaluate_quotation_rows(rows, today=ref_today)


def scan_so_fulfillment(company: str | None = None, today: date | None = None) -> list[dict]:
    """Query live Sales Order rows and evaluate fulfillment monitor findings."""
    comp = _resolve_company(company)
    ref_today = getdate(today or nowdate())
    max_date = add_days(ref_today, SO_WARNING_DAYS)

    rows = frappe.get_all(
        "Sales Order",
        filters={
            "company": comp,
            "docstatus": 1,
            "status": ["in", ["To Deliver and Bill", "To Deliver"]],
            "per_delivered": ["<", 100],
            "delivery_date": ["<=", str(max_date)],
        },
        fields=[
            "name",
            "customer",
            "customer_name",
            "delivery_date",
            "status",
            "docstatus",
            "per_delivered",
            "base_grand_total",
        ],
        limit_page_length=0,
    )
    return evaluate_so_rows(rows, today=ref_today)


def scan_delivered_unbilled(company: str | None = None, today: date | None = None) -> list[dict]:
    """Query live Delivery Note rows and evaluate delivered-but-unbilled findings."""
    comp = _resolve_company(company)
    ref_today = getdate(today or nowdate())
    max_posting_date = add_days(ref_today, -DN_UNBILLED_MIN_AGE_DAYS)

    rows = frappe.get_all(
        "Delivery Note",
        filters={
            "company": comp,
            "docstatus": 1,
            "is_return": 0,
            "status": ["in", ["To Bill", "Partially Billed"]],
            "per_billed": ["<", 100],
            "posting_date": ["<=", str(max_posting_date)],
        },
        fields=[
            "name",
            "customer",
            "customer_name",
            "posting_date",
            "status",
            "docstatus",
            "per_billed",
            "is_return",
            "base_grand_total",
        ],
        limit_page_length=0,
    )
    return evaluate_dn_rows(rows, today=ref_today)


def scan_all_sales_detectors(company: str | None = None, today: date | None = None) -> list[dict]:
    """Run all 7 Sales detectors (Tahap 1 + Tahap 2) and return combined findings."""
    ref_today = getdate(today or nowdate())
    comp = _resolve_company(company)
    findings = []
    findings.extend(scan_quotation_followup(company=comp, today=ref_today))
    findings.extend(scan_so_fulfillment(company=comp, today=ref_today))
    findings.extend(scan_delivered_unbilled(company=comp, today=ref_today))
    findings.extend(scan_churn(company=comp, today=ref_today))
    findings.extend(scan_purchase_pattern(company=comp, today=ref_today))
    findings.extend(scan_pricing_anomaly(company=comp, today=ref_today))
    findings.extend(scan_drafting(company=comp, today=ref_today))
    return findings


def _heartbeat_cache_key(user: str) -> str:
    return f"aios:desk_heartbeat:{user}"


def record_desk_heartbeat(user: str) -> str:
    """Record lightweight Desk presence ping (zero LLM, zero token cost)."""
    ts = now_datetime().isoformat()
    frappe.cache.set_value(_heartbeat_cache_key(user), ts, expires_in_sec=HEARTBEAT_TIMEOUT_SECONDS * 2)
    return ts


def is_user_away_from_desk(user: str, now_dt: datetime | None = None) -> bool:
    """Return True when Desk heartbeat has stopped for >= 5 minutes (or never sent)."""
    raw = frappe.cache.get_value(_heartbeat_cache_key(user))
    if not raw:
        return True
    try:
        last_dt = get_datetime(raw)
        ref_now = now_dt or now_datetime()
        return (ref_now - last_dt).total_seconds() >= HEARTBEAT_TIMEOUT_SECONDS
    except Exception as exc:
        log_exception("AIOS Sales Heartbeat Parse", exc=exc, context=f"user={user}")
        return True


def get_sales_proactive_recipients() -> list[str]:
    """Return active AIOS client recipients (AIOS Channel Receiver -> AIOS Client Owner)."""
    return notify.get_channel_recipients()


def _create_sales_proactive_conversation(user: str, insight_date: str | None = None) -> str:
    """Create a fresh Sales AIOS Conversation per proactive scan for Desk delivery."""
    target_date = str(getdate(insight_date or nowdate()))
    conv = frappe.get_doc(
        {
            "doctype": "AIOS Conversation",
            "user": user,
            "branch": SALES_BRANCH,
            "title": f"Ringkasan Proaktif Sales {target_date}",
        }
    ).insert(ignore_permissions=True)
    return str(conv.name)


def _insert_desk_insight_message(user: str, content: str, insight_date: str | None = None) -> str:
    conv_name = _create_sales_proactive_conversation(user, insight_date=insight_date)
    frappe.get_doc(
        {
            "doctype": "AIOS Message",
            "conversation": conv_name,
            "role": "manager",
            "worker_key": "manager",
            "content": content,
        }
    ).insert(ignore_permissions=True)
    return conv_name


_DETECTOR_LABELS = (
    ("quotation_followup", "Follow-up Penawaran"),
    ("so_fulfillment", "Monitor Pengiriman SO"),
    ("delivered_unbilled", "Surat Jalan Belum Ditagih"),
    ("churn_reactivation", "Churn & Reaktivasi"),
    ("purchase_pattern_reorder", "Pola Pembelian"),
    ("pricing_discount_anomaly", "Anomali Harga"),
    ("intelligent_drafting", "Usulan Draf"),
)


def _format_finding_timing(finding: dict) -> str:
    rule_key = str(finding.get("rule_key") or "")
    if rule_key == "quotation_followup":
        delta = int(finding.get("days_delta") or 0)
        if delta > 0:
            return f"berlaku {delta} hari lagi"
        if delta == 0:
            return "berakhir hari ini"
        return f"kedaluwarsa {abs(delta)} hari lalu"
    if rule_key == "so_fulfillment":
        delta = int(finding.get("days_delta") or 0)
        if delta < 0:
            return f"terlambat {abs(delta)} hari"
        if delta == 0:
            return "jatuh tempo hari ini"
        return f"waspada {delta} hari lagi"
    if rule_key == "delivered_unbilled":
        age = int(finding.get("age_days") or 0)
        return f"umur {age} hari"
    if rule_key == "churn_reactivation":
        return f"tidak beli {int(finding.get('days_since_purchase') or 0)} hari"
    if rule_key == "purchase_pattern_reorder":
        return f"pola {int(finding.get('median_interval_days') or 0)} hari"
    if rule_key == "pricing_discount_anomaly":
        return f"selisih {abs(float(finding.get('deviation_percent') or 0.0)):.2f}%"
    if rule_key == "intelligent_drafting":
        return f"usulan {finding.get('draft_doctype') or 'draf'}"
    return "-"


def build_proactive_summary(findings: list[dict], insight_date: str | None = None) -> str:
    """Build one deterministic summary message (no LLM) for a scan batch."""
    target_date = str(getdate(insight_date or nowdate()))
    lines = [f"Ringkasan Insight Proaktif Sales ({target_date})", ""]

    for rule_key, label in _DETECTOR_LABELS:
        group = [f for f in findings if f.get("rule_key") == rule_key]
        if not group:
            continue
        total_val = sum(float(f.get("base_grand_total") or 0.0) for f in group)
        lines.append(f"- {label}: {len(group)} dokumen (Total {_format_currency_amount(total_val)})")

    top_five = sorted(
        findings,
        key=lambda f: (-float(f.get("base_grand_total") or 0.0), str(f.get("name") or "")),
    )[:5]
    if top_five:
        lines.append("")
        lines.append("5 Temuan Teratas (nilai terbesar):")
        for idx, item in enumerate(top_five, start=1):
            demo_prefix = "[DEMO] " if (item.get("is_demo") or _is_demo_row(item)) else ""
            doc_name = str(item.get("name") or "-")
            customer = str(item.get("customer_name") or "-")
            val_str = _format_currency_amount(float(item.get("base_grand_total") or 0.0))
            timing_str = _format_finding_timing(item)
            lines.append(f"{idx}. {demo_prefix}{doc_name} | {customer} | {val_str} | {timing_str}")

    lines.append("")
    lines.append("Catatan: Pemberitahuan proaktif saja; tidak ada draf yang dibuat otomatis.")
    return "\n".join(lines)


def _deliver_summary_to_user(user: str, summary_text: str, insight_date: str | None = None) -> dict:
    """Route one summary message to either Desk OR Telegram (never both)."""
    summary = str(summary_text or "").strip()
    away = is_user_away_from_desk(user)

    if not away:
        conv_name = _insert_desk_insight_message(user, summary, insight_date=insight_date)
        return {
            "status": "SENT_DESK",
            "channel": "desk",
            "conversation": conv_name,
            "is_read": 0,
            "reason": "",
        }

    targets = notify._get_linked_telegram_targets([user])
    if not targets:
        reason = "Pengguna jauh dari Desk dan belum menautkan Telegram; insight disimpan di Desk."
        log_exception("AIOS Sales Proactive Telegram Skipped", context=f"user={user}; {reason}")
        conv_name = _insert_desk_insight_message(user, summary, insight_date=insight_date)
        return {
            "status": "SENT_DESK",
            "channel": "desk",
            "conversation": conv_name,
            "is_read": 0,
            "reason": reason,
        }

    _, chat_id = targets[0]
    sent = telegram_client.send_message(chat_id, summary)
    if not sent:
        raise RuntimeError(f"Gagal mengirim pesan Telegram ke chat_id={chat_id}")
    return {
        "status": "SENT_TELEGRAM",
        "channel": "telegram",
        "conversation": None,
        "is_read": 1,
        "reason": "",
    }


def dispatch_proactive_findings(findings: list[dict], insight_date: str | None = None) -> dict:
    """Filter per-document dedup, send 1 summary per scan per recipient, and log per document."""
    target_date = str(getdate(insight_date or nowdate()))
    recipients = get_sales_proactive_recipients()
    stats = {
        "total_findings": len(findings),
        "recipients": len(recipients),
        "messages_sent": 0,
        "sent": 0,
        "skipped_dedup": 0,
        "failed": 0,
    }
    if not findings:
        return stats

    for user in recipients:
        new_findings: list[dict] = []
        for finding in findings:
            rule_key = str(finding.get("rule_key") or "")
            ref_doctype = str(finding.get("reference_doctype") or "")
            ref_name = str(finding.get("name") or "")
            if rule_key == "churn_reactivation" and is_churn_deduped(ref_name, user, target_date):
                stats["skipped_dedup"] += 1
                continue
            existing = frappe.db.get_value(
                INSIGHT_LOG_DOCTYPE,
                {
                    "rule_key": rule_key,
                    "reference_doctype": ref_doctype,
                    "reference_name": ref_name,
                    "insight_date": target_date,
                    "recipient_user": user,
                    "status": ["in", ["SENT_DESK", "SENT_TELEGRAM"]],
                },
                "name",
            )
            if existing:
                stats["skipped_dedup"] += 1
                continue
            new_findings.append(finding)

        if not new_findings:
            continue

        log_docs = []
        for finding in new_findings:
            log_doc = frappe.get_doc(
                {
                    "doctype": INSIGHT_LOG_DOCTYPE,
                    "rule_key": str(finding.get("rule_key") or ""),
                    "reference_doctype": str(finding.get("reference_doctype") or ""),
                    "reference_name": str(finding.get("name") or ""),
                    "insight_date": target_date,
                    "recipient_user": user,
                    "status": "PENDING",
                    "is_read": 0,
                }
            ).insert(ignore_permissions=True)
            log_docs.append(log_doc)
        if not frappe.flags.in_test:
            frappe.db.commit()

        summary_text = build_proactive_summary(new_findings, insight_date=target_date)
        try:
            outcome = _deliver_summary_to_user(user, summary_text, insight_date=target_date)
            is_desk = outcome["status"] == "SENT_DESK"
            for idx, log_doc in enumerate(log_docs):
                log_doc.status = outcome["status"]
                log_doc.channel = outcome.get("channel") or ""
                log_doc.conversation = outcome.get("conversation")
                # Only 1 row per summary batch carries is_read=0 so Desk badge = 1 per scan
                log_doc.is_read = (0 if idx == 0 else 1) if is_desk else 1
                log_doc.reason = outcome.get("reason") or ""
                log_doc.save(ignore_permissions=True)
            if not frappe.flags.in_test:
                frappe.db.commit()
            stats["messages_sent"] += 1
            stats["sent"] += len(log_docs)
        except Exception as exc:
            log_exception(
                "AIOS Sales Proactive Dispatch",
                exc=exc,
                context=f"user={user}; count={len(log_docs)}",
            )
            for log_doc in log_docs:
                log_doc.status = "FAILED"
                log_doc.reason = str(exc)[:140]
                log_doc.save(ignore_permissions=True)
            if not frappe.flags.in_test:
                frappe.db.commit()
            stats["failed"] += len(log_docs)

    return stats


def run_daily_sales_proactive_scan(company: str | None = None, today: date | None = None) -> dict:
    """Scheduled daily entry point for Stage 1 Sales proactive insights."""
    ref_today = getdate(today or nowdate())
    findings = scan_all_sales_detectors(company=company, today=ref_today)
    dispatch_stats = dispatch_proactive_findings(findings, insight_date=str(ref_today))
    return {
        "status": "success",
        "insight_date": str(ref_today),
        "findings_count": len(findings),
        "findings": findings,
        **dispatch_stats,
    }



# ---------------------------------------------------------------------------
# Tahap 2 — Churn, Purchase Pattern, Pricing Anomaly, Drafting, scheduler
# ---------------------------------------------------------------------------

# Thresholds locked by Ten (K1-K7)
CHURN_DAYS = 75
CHURN_DEDUP_DAYS = 7
PATTERN_MIN_PURCHASES = 3
PATTERN_WINDOW_DAYS = 7
PRICING_DISCOUNT_THRESHOLD = 20.0
DRAFTING_VALID_DAYS = 14
# ponytail: jendela lookback Churn/Drafting dipilih builder (730/180 hari) supaya
# pemindaian tidak menyeret seluruh riwayat; angkanya bisa diubah Ten tanpa
# menyentuh logika.
DRAFTING_LOOKBACK_DAYS = 180
CHURN_LOOKBACK_DAYS = 730

DETECTOR_KEYS = (
    "quotation_followup",
    "so_fulfillment",
    "delivered_unbilled",
    "churn_reactivation",
    "purchase_pattern_reorder",
    "pricing_discount_anomaly",
    "intelligent_drafting",
)


def _composite_key(customer: str, item_code: str) -> str:
    """Reference name komposit untuk temuan yang acuannya customer + item."""
    return f"{customer}::{item_code}"


def _median_interval_days(purchase_dates: list) -> int | None:
    """Median jarak hari antar pembelian; None bila kurang dari 2 interval."""
    dates = sorted(getdate(d) for d in purchase_dates if d)
    gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    gaps = [g for g in gaps if g > 0]
    if len(gaps) < 2:
        return None
    gaps.sort()
    mid = len(gaps) // 2
    if len(gaps) % 2 == 1:
        return int(gaps[mid])
    return int(round((gaps[mid - 1] + gaps[mid]) / 2.0))


def evaluate_churn_rows(
    rows: list[dict], today: date | None = None, threshold_days: int | None = None
) -> list[dict]:
    """Evaluate per-customer purchase recency rows into churn findings (K1)."""
    ref_today = getdate(today or nowdate())
    limit_days = int(threshold_days if threshold_days is not None else CHURN_DAYS)
    findings: list[dict] = []

    for row in rows:
        customer = str(row.get("customer") or "").strip()
        if not customer:
            continue
        last_raw = row.get("last_purchase_date")
        if not last_raw:
            continue
        last_dt = getdate(last_raw)
        days_since = (ref_today - last_dt).days
        if days_since < limit_days:
            continue

        customer_name = str(row.get("customer_name") or customer)
        total = float(row.get("total_value") or 0.0)
        invoice_count = int(row.get("invoice_count") or 0)
        is_demo = _is_demo_row({"customer_name": customer_name, "name": customer})
        prefix = "[DEMO] " if is_demo else ""
        findings.append(
            {
                "rule_key": "churn_reactivation",
                "reference_doctype": "Customer",
                "name": customer,
                "customer_name": customer_name,
                "last_purchase_date": str(last_dt),
                "days_since_purchase": days_since,
                "invoice_count": invoice_count,
                "base_grand_total": total,
                "severity": "churn",
                "is_demo": is_demo,
                "summary": (
                    f"{prefix}Churn & Reaktivasi {customer} ({customer_name}) — "
                    f"tidak membeli {days_since} hari (terakhir {last_dt}), "
                    f"nilai historis {_format_currency_amount(total)} dari {invoice_count} invoice."
                ),
            }
        )

    return _sort_findings(findings, "last_purchase_date")


def is_churn_deduped(customer: str, user: str, insight_date: str | None = None) -> bool:
    """K3: Churn untuk customer yang sama dikirim ulang paling cepat 7 hari sekali."""
    target = getdate(insight_date or nowdate())
    sent_dates = frappe.get_all(
        INSIGHT_LOG_DOCTYPE,
        filters={
            "rule_key": "churn_reactivation",
            "reference_doctype": "Customer",
            "reference_name": customer,
            "recipient_user": user,
            "status": ["in", ["SENT_DESK", "SENT_TELEGRAM"]],
        },
        pluck="insight_date",
    )
    for raw in sent_dates:
        if not raw:
            continue
        if 0 <= (target - getdate(raw)).days < CHURN_DEDUP_DAYS:
            return True
    return False


def evaluate_purchase_pattern_rows(rows: list[dict], today: date | None = None) -> list[dict]:
    """Evaluate purchase history rows: reorder due when today >= last + median - 7 (K4)."""
    ref_today = getdate(today or nowdate())
    findings: list[dict] = []

    for row in rows:
        customer = str(row.get("customer") or "").strip()
        item_code = str(row.get("item_code") or "").strip()
        dates = [d for d in (row.get("purchase_dates") or []) if d]
        if not customer or not item_code:
            continue
        if len(dates) < PATTERN_MIN_PURCHASES:
            continue
        median = _median_interval_days(dates)
        if median is None:
            continue
        last_dt = max(getdate(d) for d in dates)
        due_date = getdate(add_days(last_dt, median - PATTERN_WINDOW_DAYS))
        if ref_today < due_date:
            continue

        customer_name = str(row.get("customer_name") or customer)
        qty_total = float(row.get("qty_total") or 0.0)
        avg_rate = float(row.get("avg_rate") or 0.0)
        is_demo = _is_demo_row({"customer_name": customer_name, "name": customer})
        prefix = "[DEMO] " if is_demo else ""
        findings.append(
            {
                "rule_key": "purchase_pattern_reorder",
                "reference_doctype": "Customer",
                "name": _composite_key(customer, item_code),
                "customer_name": customer_name,
                "item_code": item_code,
                "purchase_count": len(dates),
                "median_interval_days": median,
                "last_purchase_date": str(last_dt),
                "due_date": str(due_date),
                "qty_total": qty_total,
                "base_grand_total": qty_total * avg_rate,
                "severity": "reorder_due",
                "is_demo": is_demo,
                "summary": (
                    f"{prefix}Pola Pembelian {customer_name} — {item_code} biasanya dibeli "
                    f"tiap {median} hari ({len(dates)} pembelian, terakhir {last_dt}); "
                    f"perkiraan jatuh tempo {due_date}."
                ),
            }
        )

    return _sort_findings(findings, "due_date")


def evaluate_pricing_anomaly_rows(rows: list[dict], today: date | None = None) -> list[dict]:
    """Evaluate item rows against price_list_rate: discount > 20% or overprice (K5/K6)."""
    findings: list[dict] = []

    for row in rows:
        # Jebakan 1: harga pembanding kosong/nol -> tidak ada pembanding, bukan anomali.
        price_list_rate = float(row.get("price_list_rate") or 0.0)
        if price_list_rate <= 0:
            continue
        # Jebakan 2: diskon sah dari Pricing Rule bukan anomali.
        if str(row.get("pricing_rules") or "").strip():
            continue

        parent = str(row.get("parent") or "").strip()
        item_code = str(row.get("item_code") or "").strip()
        if not parent or not item_code:
            continue

        rate = float(row.get("rate") or 0.0)
        discount_pct = float(row.get("discount_percentage") or 0.0)
        deviation = (rate - price_list_rate) / price_list_rate * 100.0

        if discount_pct > PRICING_DISCOUNT_THRESHOLD:
            anomaly_type = "discount"
            deviation_percent = -abs(discount_pct)
        elif deviation > PRICING_DISCOUNT_THRESHOLD:
            anomaly_type = "overprice"
            deviation_percent = round(deviation, 2)
        else:
            continue

        parenttype = str(row.get("parenttype") or "")
        customer_name = str(row.get("customer_name") or "-")
        delta_amount = abs(rate - price_list_rate) * float(row.get("qty") or 1.0)
        is_demo = _is_demo_row({"customer_name": customer_name, "name": parent})
        prefix = "[DEMO] " if is_demo else ""
        label = "diskon" if anomaly_type == "discount" else "harga di atas standar"
        findings.append(
            {
                "rule_key": "pricing_discount_anomaly",
                "reference_doctype": parenttype,
                "name": _composite_key(parent, item_code),
                "parent": parent,
                "customer_name": customer_name,
                "item_code": item_code,
                "anomaly_type": anomaly_type,
                "deviation_percent": deviation_percent,
                "rate": rate,
                "price_list_rate": price_list_rate,
                "base_grand_total": delta_amount,
                "severity": anomaly_type,
                "is_demo": is_demo,
                "summary": (
                    f"{prefix}Anomali Harga {parent} ({customer_name}) item {item_code} — "
                    f"{label} {abs(deviation_percent):.2f}% "
                    f"(harga {_format_currency_amount(rate)} vs standar {_format_currency_amount(price_list_rate)})."
                ),
            }
        )

    return _sort_findings_by_value(findings)


def build_drafting_payload(row: dict, doctype: str, today: date | None = None) -> dict:
    """Build a Pending Action Draft payload from the last purchase; never inserts it (K7)."""
    if doctype not in {"Quotation", "Sales Order"}:
        raise ValueError(f"DocType draf tidak didukung untuk Drafting: {doctype}")

    ref_today = getdate(today or nowdate())
    valid_till = str(add_days(ref_today, DRAFTING_VALID_DAYS))
    customer = str(row.get("customer") or "").strip()
    items = [
        {
            "item_code": str(item.get("item_code") or ""),
            "qty": float(item.get("qty") or 0.0),
            "rate": float(item.get("rate") or 0.0),
        }
        for item in (row.get("items") or [])
        if item.get("item_code")
    ]

    if doctype == "Quotation":
        data = {
            "quotation_to": "Customer",
            "party_name": customer,
            "transaction_date": str(ref_today),
            "valid_till": valid_till,
            "items": items,
        }
    else:
        data = {
            "customer": customer,
            "transaction_date": str(ref_today),
            "delivery_date": valid_till,
            "valid_till": valid_till,
            "items": items,
        }

    return {
        "doctype": doctype,
        "data": data,
        "reason": (
            f"Usulan draf dari pembelian terakhir {customer} "
            f"({row.get('last_purchase_date') or '-'})."
        ),
    }


def evaluate_drafting_rows(rows: list[dict], today: date | None = None) -> list[dict]:
    """Build Drafting suggestions that carry a ready payload but create no draft."""
    ref_today = getdate(today or nowdate())
    findings: list[dict] = []

    for row in rows:
        customer = str(row.get("customer") or "").strip()
        items = row.get("items") or []
        if not customer or not items:
            continue
        customer_name = str(row.get("customer_name") or customer)
        doctype = "Sales Order" if row.get("prefer_sales_order") else "Quotation"
        payload = build_drafting_payload(row, doctype, today=ref_today)
        total = sum(float(i.get("qty") or 0) * float(i.get("rate") or 0) for i in items)
        is_demo = _is_demo_row({"customer_name": customer_name, "name": customer})
        prefix = "[DEMO] " if is_demo else ""
        findings.append(
            {
                "rule_key": "intelligent_drafting",
                "reference_doctype": "Customer",
                "name": customer,
                "customer_name": customer_name,
                "last_purchase_date": str(row.get("last_purchase_date") or ""),
                "draft_doctype": doctype,
                "draft_payload": payload,
                "item_count": len(items),
                "base_grand_total": total,
                "severity": "draft_suggestion",
                "is_demo": is_demo,
                "summary": (
                    f"{prefix}Usulan Draf {doctype} {customer_name} — {len(items)} item dari "
                    f"pembelian terakhir ({row.get('last_purchase_date') or '-'}), "
                    f"nilai {_format_currency_amount(total)}. Draf dibuat hanya bila Anda minta."
                ),
            }
        )

    return _sort_findings(findings, "last_purchase_date")


def scan_churn(company: str | None = None, today: date | None = None) -> list[dict]:
    """Aggregate last purchase per customer from submitted Sales Invoices (K2)."""
    comp = _resolve_company(company)
    ref_today = getdate(today or nowdate())
    rows = frappe.db.sql(
        """
        SELECT si.customer AS customer,
               MAX(c.customer_name) AS customer_name,
               MAX(si.posting_date) AS last_purchase_date,
               SUM(si.base_grand_total) AS total_value,
               COUNT(si.name) AS invoice_count
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND IFNULL(si.is_return, 0) = 0
          AND si.company = %(company)s
          AND si.posting_date >= %(min_date)s
        GROUP BY si.customer
        """,
        {"company": comp, "min_date": str(add_days(ref_today, -CHURN_LOOKBACK_DAYS))},
        as_dict=True,
    )
    return evaluate_churn_rows(rows or [], today=ref_today)


def scan_purchase_pattern(company: str | None = None, today: date | None = None) -> list[dict]:
    """Aggregate per customer+item purchase dates from submitted Sales Invoices."""
    comp = _resolve_company(company)
    ref_today = getdate(today or nowdate())
    rows = frappe.db.sql(
        """
        SELECT si.customer AS customer,
               MAX(c.customer_name) AS customer_name,
               sii.item_code AS item_code,
               si.posting_date AS posting_date,
               SUM(sii.qty) AS qty,
               AVG(sii.rate) AS rate
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND IFNULL(si.is_return, 0) = 0
          AND si.company = %(company)s
          AND si.posting_date >= %(min_date)s
        GROUP BY si.customer, sii.item_code, si.posting_date
        """,
        {"company": comp, "min_date": str(add_days(ref_today, -CHURN_LOOKBACK_DAYS))},
        as_dict=True,
    )

    grouped: dict[tuple, dict] = {}
    for row in rows or []:
        key = (str(row.get("customer") or ""), str(row.get("item_code") or ""))
        if not key[0] or not key[1]:
            continue
        bucket = grouped.setdefault(
            key,
            {
                "customer": key[0],
                "customer_name": row.get("customer_name") or key[0],
                "item_code": key[1],
                "purchase_dates": [],
                "qty_total": 0.0,
                "_rate_sum": 0.0,
                "_rate_n": 0,
            },
        )
        bucket["purchase_dates"].append(str(row.get("posting_date")))
        bucket["qty_total"] += float(row.get("qty") or 0.0)
        bucket["_rate_sum"] += float(row.get("rate") or 0.0)
        bucket["_rate_n"] += 1

    for bucket in grouped.values():
        n = bucket.pop("_rate_n") or 1
        bucket["avg_rate"] = bucket.pop("_rate_sum") / n

    return evaluate_purchase_pattern_rows(list(grouped.values()), today=ref_today)


def scan_pricing_anomaly(company: str | None = None, today: date | None = None) -> list[dict]:
    """Scan item rows in Quotation / Sales Order / Sales Invoice against price_list_rate."""
    comp = _resolve_company(company)
    ref_today = getdate(today or nowdate())
    min_date = str(add_days(ref_today, -DRAFTING_LOOKBACK_DAYS))
    targets = (
        ("Quotation", "Quotation Item", "transaction_date"),
        ("Sales Order", "Sales Order Item", "transaction_date"),
        ("Sales Invoice", "Sales Invoice Item", "posting_date"),
    )
    rows: list[dict] = []
    for parent_doctype, child_doctype, date_field in targets:
        rows.extend(
            frappe.db.sql(
                f"""
                SELECT child.parent AS parent,
                       %(parenttype)s AS parenttype,
                       child.item_code AS item_code,
                       child.qty AS qty,
                       child.rate AS rate,
                       child.price_list_rate AS price_list_rate,
                       child.discount_percentage AS discount_percentage,
                       child.pricing_rules AS pricing_rules,
                       parent.customer_name AS customer_name
                FROM `tab{child_doctype}` child
                INNER JOIN `tab{parent_doctype}` parent ON parent.name = child.parent
                WHERE parent.docstatus = 1
                  AND parent.company = %(company)s
                  AND parent.{date_field} >= %(min_date)s
                  AND IFNULL(child.price_list_rate, 0) > 0
                """,
                {"company": comp, "min_date": min_date, "parenttype": parent_doctype},
                as_dict=True,
            )
            or []
        )

    return evaluate_pricing_anomaly_rows(rows, today=ref_today)


def scan_drafting(company: str | None = None, today: date | None = None) -> list[dict]:
    """Suggest drafts from each customer latest purchase; creates zero drafts."""
    comp = _resolve_company(company)
    ref_today = getdate(today or nowdate())
    latest = frappe.db.sql(
        """
        SELECT si.customer AS customer, si.name AS invoice, si.posting_date AS posting_date
        FROM `tabSales Invoice` si
        INNER JOIN (
            SELECT customer AS cust, MAX(posting_date) AS max_date
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND IFNULL(is_return, 0) = 0 AND company = %(company)s
              AND posting_date >= %(min_date)s
            GROUP BY customer
        ) newest ON newest.cust = si.customer AND newest.max_date = si.posting_date
        WHERE si.docstatus = 1 AND IFNULL(si.is_return, 0) = 0 AND si.company = %(company)s
        """,
        {
            "company": comp,
            "min_date": str(add_days(ref_today, -DRAFTING_LOOKBACK_DAYS)),
        },
        as_dict=True,
    )

    rows: list[dict] = []
    for row in latest or []:
        items = frappe.get_all(
            "Sales Invoice Item",
            filters={"parent": row.get("invoice"), "parenttype": "Sales Invoice"},
            fields=["item_code", "qty", "rate"],
        )
        if not items:
            continue
        customer_name = frappe.db.get_value("Customer", row.get("customer"), "customer_name")
        rows.append(
            {
                "customer": row.get("customer"),
                "customer_name": customer_name or row.get("customer"),
                "last_purchase_date": str(row.get("posting_date")),
                "items": items,
            }
        )

    return evaluate_drafting_rows(rows, today=ref_today)


def is_detector_due(setting: dict, now_dt=None) -> bool:
    """Pure check: should this detector run at the given moment? (K8)"""
    if not setting or not int(setting.get("enabled") or 0):
        return False

    moment = get_datetime(now_dt) if now_dt else now_datetime()
    run_hour = int(setting.get("run_hour") if setting.get("run_hour") is not None else 6)
    if moment.hour < run_hour:
        return False

    frequency = str(setting.get("frequency") or "daily").strip().lower()
    if frequency == "daily":
        return True
    if frequency == "weekly":
        target_day = str(setting.get("day_of_week") or "").strip().lower()
        if not target_day:
            return False
        return moment.strftime("%A").lower() == target_day
    if frequency == "monthly":
        return moment.day == 1
    return False


_DEFAULT_SCHEDULE = {
    "quotation_followup": ("Follow-up Penawaran", 6),
    "so_fulfillment": ("Monitor Pengiriman SO", 6),
    "delivered_unbilled": ("Surat Jalan Belum Ditagih", 6),
    "churn_reactivation": ("Churn & Reaktivasi", 7),
    "purchase_pattern_reorder": ("Pola Pembelian", 7),
    "pricing_discount_anomaly": ("Anomali Harga", 8),
    "intelligent_drafting": ("Usulan Draf", 8),
}


def default_detector_settings() -> list[dict]:
    """Jadwal bawaan saat Single DocType belum pernah disimpan."""
    return [
        {
            "detector_key": key,
            "label": label,
            "enabled": 1,
            "frequency": "daily",
            "run_hour": hour,
            "day_of_week": "",
        }
        for key, (label, hour) in _DEFAULT_SCHEDULE.items()
    ]


def get_detector_settings() -> list[dict]:
    """Read per-detector schedule settings from the Single DocType child table."""
    if not frappe.db.exists("DocType", "AIOS Proactive Detector Setting"):
        return []
    doc = frappe.get_single("AIOS Proactive Detector Setting")
    return [row.as_dict() for row in (doc.get("detectors") or [])]


def run_detector_scheduler_dispatch(today: date | None = None, now_dt=None) -> dict:
    """Hourly dispatcher: run one combined scan when any detector is due (K8/K10)."""
    ref_today = getdate(today or nowdate())
    due_keys = [
        str(s.get("detector_key") or "")
        for s in get_detector_settings()
        if s.get("detector_key") and is_detector_due(s, now_dt=now_dt)
    ]
    if not due_keys:
        return {"status": "skipped", "reason": "tidak ada detektor yang jatuh tempo", "due": []}

    result = run_daily_sales_proactive_scan(today=ref_today)
    result["due"] = due_keys
    return result


def predict_customer_churn_risk(customer: str, days_since_last_order: int | None = None) -> dict:
    """Churn risk for one customer, using the same threshold as the Churn detector (K11)."""
    customer = str(customer or "").strip()
    if not customer:
        frappe.throw("customer wajib diisi.")

    last_date = None
    if days_since_last_order is None:
        last_date = frappe.db.get_value(
            "Sales Invoice",
            {"customer": customer, "docstatus": 1, "is_return": 0},
            "posting_date",
            order_by="posting_date desc",
        )
        days = (getdate(nowdate()) - getdate(last_date)).days if last_date else None
    else:
        days = int(days_since_last_order)
        if days < 0:
            frappe.throw("days_since_last_order tidak boleh negatif.")

    if days is None:
        risk_level = "UNKNOWN"
    elif days >= CHURN_DAYS:
        risk_level = "HIGH"
    elif days >= CHURN_DAYS // 2:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    recommendation = {
        "HIGH": "Kirim penawaran reaktivasi.",
        "MEDIUM": "Jadwalkan tindak lanjut.",
        "LOW": "Tidak perlu tindakan khusus.",
    }.get(risk_level, "Belum ada pembelian tercatat; data tidak cukup untuk menilai risiko.")

    return {
        "customer": customer,
        "customer_name": frappe.db.get_value("Customer", customer, "customer_name") or customer,
        "days_since_last_order": days,
        "last_order_date": str(last_date) if last_date else None,
        "churn_threshold_days": CHURN_DAYS,
        "risk_level": risk_level,
        "recommendation": recommendation,
    }
