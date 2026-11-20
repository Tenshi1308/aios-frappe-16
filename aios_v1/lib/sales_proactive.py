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
    """Run all 3 live Stage 1 Sales detectors and return combined findings."""
    ref_today = getdate(today or nowdate())
    comp = _resolve_company(company)
    findings = []
    findings.extend(scan_quotation_followup(company=comp, today=ref_today))
    findings.extend(scan_so_fulfillment(company=comp, today=ref_today))
    findings.extend(scan_delivered_unbilled(company=comp, today=ref_today))
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
