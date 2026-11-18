"""
Detail dokumen transaksi untuk SPA (keputusan pemilik 11 Nov 2026): setiap baris transaksi di daftar dapat diklik untuk
melihat detailnya dulu, tidak hanya lewat tombol aksi.

Satu endpoint ``get_transaction_detail(doctype, name)`` mengembalikan bentuk seragam yang dirender
``frontend/src/features/transactions/TransactionDetailModal.vue``::

    {doctype, name, title, subtitle, status: {label, variant}, fields: [{label, value, type}],
     tables: [{title, columns: [{key, label, type}], rows: [...]}], totals: [{label, value, strong}],
     print_kind, links: [{doctype, name, label}]}

Izin mengikuti halaman asal tiap DocType (tidak ada akses baru):
- Sales Invoice  — Tagihan SPP (``invoice_print._scope``: BM/Principal/Finance/CSO) atau murid/wali pemiliknya.
- Payment Entry  — sama dengan Sales Invoice; murid/wali hanya pembayaran anaknya.
- SPI Payment Submission — antrean Pembayaran SPP (``spp_payment._ops_scope``).
- Journal Entry  — data keuangan (finto_edu ``fee._get_company_scope``: BM/Principal/Finance).
- Payroll Entry, Additional Salary — penggajian (``payroll._payroll_scope``).
- SPI Teacher Fee Payout — dompet honor (admin honor; guru hanya miliknya).
- Student Transfer — mutasi (finto_edu ``student_transfer._get_company_scope``, cabang asal atau tujuan).
Spec: docs/specs/TRANSACTION_DETAIL.md.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr, flt, strip_html

from spi_fintoedu.access import learner_students

SUPPORTED = (
	"Sales Invoice", "Payment Entry", "SPI Payment Submission", "Journal Entry",
	"Payroll Entry", "Additional Salary", "SPI Teacher Fee Payout", "Student Transfer",
)
DOCSTATUS_LABEL = {0: ("Draf", "secondary"), 2: ("Dibatalkan", "dark")}


def _deny():
	frappe.throw(_("Anda tidak memiliki akses ke dokumen ini."), frappe.PermissionError)


def _check_company(scope: list[str] | None, company: str | None) -> None:
	if scope is not None and company not in scope:
		_deny()


def _student_customers(students: list[str]) -> set[str]:
	return set(frappe.get_all("Student", filters={"name": ["in", students or [""]]}, pluck="customer"))


def _assert_access(doc) -> None:
	learners = learner_students()
	if doc.doctype in ("Sales Invoice", "Payment Entry"):
		if learners is not None:
			if doc.doctype == "Sales Invoice" and doc.get("student") in learners:
				return
			if doc.doctype == "Payment Entry" and doc.party_type == "Customer" and doc.party in _student_customers(learners):
				return
			_deny()
		from spi_fintoedu.api.invoice_print import _scope

		_check_company(_scope()[0], doc.company)
		return
	if learners is not None:
		_deny()
	if doc.doctype == "SPI Payment Submission":
		from spi_fintoedu.api.spp_payment import _ops_scope

		_ops_scope(doc.company)  # PermissionError bila cabang di luar cakupan
		return
	if doc.doctype == "Journal Entry":
		from finto_edu.services.fee import _get_company_scope

		_check_company(_get_company_scope(), doc.company)
		return
	if doc.doctype in ("Payroll Entry", "Additional Salary"):
		from spi_fintoedu.api.payroll import _payroll_scope

		_check_company(_payroll_scope(), doc.company)
		return
	if doc.doctype == "SPI Teacher Fee Payout":
		from spi_fintoedu.api.fee_wallet import _resolve_instructor

		own = _resolve_instructor(doc.instructor)  # admin honor: apa adanya; guru: miliknya sendiri
		if own != doc.instructor:
			_deny()
		return
	if doc.doctype == "Student Transfer":
		from finto_edu.services.student_transfer import _get_company_scope as transfer_scope

		scope = transfer_scope()
		if scope is not None and doc.source_company not in scope and doc.target_company not in scope:
			_deny()
		return
	_deny()


def _status(doc, label: str | None = None, variant: str = "primary") -> dict[str, str]:
	if doc.docstatus in DOCSTATUS_LABEL:
		lab, var = DOCSTATUS_LABEL[doc.docstatus]
		return {"label": lab, "variant": var}
	return {"label": label or _("Diterbitkan"), "variant": variant}


def _f(label: str, value: Any, type_: str = "text") -> dict[str, Any]:
	return {"label": label, "value": value, "type": type_}


@frappe.whitelist(methods=["GET"])
def get_transaction_detail(doctype: str, name: str) -> dict[str, Any]:
	if doctype not in SUPPORTED:
		frappe.throw(_("Jenis dokumen {0} belum didukung.").format(doctype), frappe.ValidationError)
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} tidak ditemukan.").format(doctype, name), frappe.DoesNotExistError)
	doc = frappe.get_doc(doctype, name)
	_assert_access(doc)
	builder = {
		"Sales Invoice": _sales_invoice,
		"Payment Entry": _payment_entry,
		"SPI Payment Submission": _submission,
		"Journal Entry": _journal_entry,
		"Payroll Entry": _payroll_entry,
		"Additional Salary": _additional_salary,
		"SPI Teacher Fee Payout": _fee_payout,
		"Student Transfer": _student_transfer,
	}[doctype]
	out = builder(doc)
	out.setdefault("doctype", doctype)
	out.setdefault("name", doc.name)
	out.setdefault("links", [])
	out.setdefault("totals", [])
	out.setdefault("print_kind", None)
	return out


# ---------------------------------------------------------------- builder per DocType


def _sales_invoice(doc) -> dict[str, Any]:
	from spi_fintoedu.api.invoice_print import _payments, _print_kind

	student_name = frappe.db.get_value("Student", doc.get("student"), "student_name") if doc.get("student") else None
	grand, out = flt(doc.grand_total), flt(doc.outstanding_amount)
	if doc.docstatus == 1:
		label, variant = (
			(_("Lunas"), "success") if out <= 0 else (_("Sebagian"), "warning") if out < grand else (_("Belum Bayar"), "danger")
		)
	else:
		label, variant = None, "primary"
	payments = _payments(doc.name) if doc.docstatus == 1 else []
	return {
		"title": _("Tagihan {0}").format(doc.name),
		"subtitle": student_name or doc.customer_name,
		"status": _status(doc, label, variant),
		"fields": [
			_f(_("Murid"), f"{student_name} ({doc.student})" if doc.get("student") else doc.customer_name),
			_f(_("Cabang"), doc.company),
			_f(_("Tanggal"), doc.posting_date, "date"),
			_f(_("Jatuh tempo"), doc.due_date, "date"),
			_f(_("Program"), doc.get("custom_program")),
			_f(_("Tahun ajaran"), doc.get("custom_academic_year")),
			_f(_("Catatan"), strip_html(cstr(doc.remarks)) if doc.remarks and doc.remarks != "No Remarks" else None),
			_f(_("Alasan pembatalan"), doc.get("custom_cancel_reason")),
		],
		"tables": [
			{
				"title": _("Rincian tagihan"),
				"columns": [
					{"key": "description", "label": _("Keterangan")},
					{"key": "period", "label": _("Periode")},
					{"key": "qty", "label": _("Qty"), "type": "number"},
					{"key": "rate", "label": _("Harga"), "type": "currency"},
					{"key": "amount", "label": _("Jumlah"), "type": "currency"},
				],
				"rows": [
					{
						"description": strip_html(cstr(it.description)) or it.item_name,
						"period": it.get("custom_fee_periods"),
						"qty": flt(it.qty),
						"rate": flt(it.rate),
						"amount": flt(it.amount),
					}
					for it in doc.items
				],
			},
			{
				"title": _("Pembayaran"),
				"empty": _("Belum ada pembayaran."),
				"columns": [
					{"key": "date", "label": _("Tanggal"), "type": "date"},
					{"key": "name", "label": _("No. Pembayaran"), "link": "Payment Entry"},
					{"key": "mode", "label": _("Cara bayar")},
					{"key": "reference", "label": _("Referensi")},
					{"key": "amount", "label": _("Jumlah"), "type": "currency"},
				],
				"rows": [{**p, "date": str(p["date"])} for p in payments],
			},
		],
		"totals": [
			{"label": _("Total tagihan"), "value": grand, "strong": True},
			{"label": _("Sudah dibayar"), "value": max(grand - out, 0) if doc.docstatus == 1 else 0},
			{"label": _("Sisa tagihan"), "value": out if doc.docstatus == 1 else grand, "strong": True},
		],
		"print_kind": _print_kind(doc.docstatus, out),
	}


def _payment_entry(doc) -> dict[str, Any]:
	student = frappe.db.get_value("Student", {"customer": doc.party}, ["name", "student_name"], as_dict=True) if doc.party_type == "Customer" else None
	return {
		"title": _("Pembayaran {0}").format(doc.name),
		"subtitle": (student.student_name if student else doc.party_name) or doc.party,
		"status": _status(doc, _("Tercatat"), "success"),
		"fields": [
			_f(_("Murid / pihak"), f"{student.student_name} ({student.name})" if student else doc.party_name or doc.party),
			_f(_("Cabang"), doc.company),
			_f(_("Tanggal"), doc.posting_date, "date"),
			_f(_("Cara bayar"), doc.mode_of_payment),
			_f(_("Masuk ke akun"), doc.paid_to),
			_f(_("No. referensi"), doc.reference_no),
			_f(_("Tanggal referensi"), doc.reference_date, "date"),
			_f(_("Bukti"), doc.get("custom_spp_proof"), "file"),
			_f(_("Keterangan"), cstr(doc.remarks) or None),
		],
		"tables": [
			{
				"title": _("Dialokasikan ke tagihan"),
				"empty": _("Belum dialokasikan — seluruhnya menjadi saldo murid."),
				"columns": [
					{"key": "reference_name", "label": _("Tagihan"), "link": "Sales Invoice"},
					{"key": "due_date", "label": _("Jatuh tempo"), "type": "date"},
					{"key": "allocated_amount", "label": _("Dialokasikan"), "type": "currency"},
				],
				"rows": [
					{"reference_name": r.reference_name, "due_date": str(r.due_date) if r.due_date else None, "allocated_amount": flt(r.allocated_amount)}
					for r in doc.references
				],
			}
		],
		"totals": [
			{"label": _("Jumlah dibayar"), "value": flt(doc.paid_amount), "strong": True},
			{"label": _("Dialokasikan"), "value": flt(doc.total_allocated_amount)},
			{"label": _("Menjadi saldo murid"), "value": flt(doc.unallocated_amount)},
		],
	}


SUBMISSION_VARIANT = {
	"Menunggu Verifikasi": "warning",
	"Terverifikasi": "success",
	"Tidak Cocok": "danger",
	"Perlu Klarifikasi": "info",
	"Dibatalkan": "dark",
}


def _submission(doc) -> dict[str, Any]:
	return {
		"title": _("Pengajuan Pembayaran {0}").format(doc.name),
		"subtitle": ", ".join(cstr(r.student_name) for r in doc.lines[:3]) + (" …" if len(doc.lines) > 3 else ""),
		"status": {"label": doc.status, "variant": SUBMISSION_VARIANT.get(doc.status, "primary")},
		"fields": [
			_f(_("Cabang"), doc.company),
			_f(_("Tanggal bayar"), doc.posting_date, "date"),
			_f(_("Cara bayar"), doc.mode_of_payment),
			_f(_("Masuk ke akun"), doc.paid_to),
			_f(_("No. referensi"), doc.reference_no),
			_f(_("Bukti"), doc.proof, "file"),
			_f(_("Catatan"), doc.note),
			_f(_("Diajukan oleh"), frappe.db.get_value("User", doc.owner, "full_name") or doc.owner),
			_f(_("Diverifikasi oleh"), frappe.db.get_value("User", doc.verified_by, "full_name") if doc.verified_by else None),
			_f(_("Waktu verifikasi"), doc.verified_at, "datetime"),
			_f(_("Catatan verifikasi"), doc.verification_note),
		],
		"tables": [
			{
				"title": _("Murid"),
				"columns": [
					{"key": "student_name", "label": _("Murid")},
					{"key": "amount", "label": _("Jumlah"), "type": "currency"},
					{"key": "payment_entry", "label": _("Pembayaran"), "link": "Payment Entry"},
				],
				"rows": [{"student_name": f"{r.student_name} ({r.student})", "amount": flt(r.amount), "payment_entry": r.payment_entry} for r in doc.lines],
			}
		],
		"totals": [{"label": _("Total"), "value": flt(doc.total_amount), "strong": True}],
	}


def _journal_entry(doc) -> dict[str, Any]:
	return {
		"title": _("Jurnal {0}").format(doc.name),
		"subtitle": doc.title if doc.title != doc.name else doc.voucher_type,
		"status": _status(doc),
		"fields": [
			_f(_("Jenis"), doc.voucher_type),
			_f(_("Cabang"), doc.company),
			_f(_("Tanggal"), doc.posting_date, "date"),
			_f(_("No. referensi"), doc.cheque_no),
			_f(_("Keterangan"), cstr(doc.user_remark) or None),
		],
		"tables": [
			{
				"title": _("Baris jurnal"),
				"columns": [
					{"key": "account", "label": _("Akun")},
					{"key": "party", "label": _("Pihak")},
					{"key": "debit", "label": _("Debit"), "type": "currency"},
					{"key": "credit", "label": _("Kredit"), "type": "currency"},
					{"key": "reference", "label": _("Referensi")},
				],
				"rows": [
					{
						"account": a.account,
						"party": a.party,
						"debit": flt(a.debit_in_account_currency),
						"credit": flt(a.credit_in_account_currency),
						"reference": f"{a.reference_type} {a.reference_name}" if a.reference_type else None,
					}
					for a in doc.accounts
				],
			}
		],
		"totals": [
			{"label": _("Total debit"), "value": flt(doc.total_debit), "strong": True},
			{"label": _("Total kredit"), "value": flt(doc.total_credit), "strong": True},
		],
	}


def _payroll_entry(doc) -> dict[str, Any]:
	slips = frappe.get_all(
		"Salary Slip",
		filters={"payroll_entry": doc.name, "docstatus": ["<", 2]},
		fields=["name", "employee_name", "gross_pay", "net_pay"],
		order_by="employee_name asc",
	)
	return {
		"title": _("Proses Gaji {0}").format(doc.name),
		"subtitle": f"{doc.start_date} s/d {doc.end_date}",
		"status": _status(doc, _("Diproses"), "success"),
		"fields": [
			_f(_("Cabang"), doc.company),
			_f(_("Tanggal posting"), doc.posting_date, "date"),
			_f(_("Periode mulai"), doc.start_date, "date"),
			_f(_("Periode selesai"), doc.end_date, "date"),
			_f(_("Frekuensi"), doc.payroll_frequency),
		],
		"tables": [
			{
				"title": _("Slip gaji"),
				"empty": _("Belum ada slip."),
				"columns": [
					{"key": "name", "label": _("Slip")},
					{"key": "employee_name", "label": _("Pegawai")},
					{"key": "gross_pay", "label": _("Bruto"), "type": "currency"},
					{"key": "net_pay", "label": _("Diterima"), "type": "currency"},
				],
				"rows": [{"name": r.name, "employee_name": r.employee_name, "gross_pay": flt(r.gross_pay), "net_pay": flt(r.net_pay)} for r in slips],
			}
		],
		"totals": [
			{"label": _("Total bruto"), "value": sum(flt(r.gross_pay) for r in slips)},
			{"label": _("Total diterima"), "value": sum(flt(r.net_pay) for r in slips), "strong": True},
		],
	}


def _additional_salary(doc) -> dict[str, Any]:
	return {
		"title": _("Tambahan Gaji {0}").format(doc.name),
		"subtitle": doc.employee_name,
		"status": _status(doc, _("Tercatat"), "success"),
		"fields": [
			_f(_("Pegawai"), f"{doc.employee_name} ({doc.employee})"),
			_f(_("Cabang"), doc.company),
			_f(_("Komponen"), doc.salary_component),
			_f(_("Tanggal gaji"), doc.payroll_date, "date"),
			_f(_("Jumlah"), flt(doc.amount), "currency"),
		],
		"tables": [],
		"totals": [{"label": _("Jumlah"), "value": flt(doc.amount), "strong": True}],
	}


def _fee_payout(doc) -> dict[str, Any]:
	import json

	try:
		sessions = json.loads(doc.sessions or "[]")
	except Exception:
		sessions = []
	rows = []
	for x in sessions if isinstance(sessions, list) else []:
		if isinstance(x, dict):
			rows.append({"session": x.get("name") or x.get("session"), "date": x.get("date") or x.get("schedule_date"), "amount": x.get("fee") or x.get("amount")})
		else:
			rows.append({"session": cstr(x), "date": None, "amount": None})
	return {
		"title": _("Honor Dibayar {0}").format(doc.name),
		"subtitle": f"{doc.instructor_name} · {doc.period}",
		"status": {"label": _("Dibayar"), "variant": "success"},
		"fields": [
			_f(_("Guru"), doc.instructor_name),
			_f(_("Cabang"), doc.company),
			_f(_("Periode"), doc.period),
			_f(_("Jumlah sesi"), doc.session_count),
			_f(_("Tanggal bayar"), doc.paid_date, "date"),
			_f(_("Referensi"), doc.reference),
			_f(_("Catatan"), doc.note),
		],
		"tables": [
			{
				"title": _("Sesi"),
				"empty": _("Rincian sesi tidak tersimpan."),
				"columns": [
					{"key": "session", "label": _("Sesi")},
					{"key": "date", "label": _("Tanggal"), "type": "date"},
					{"key": "amount", "label": _("Honor"), "type": "currency"},
				],
				"rows": rows,
			}
		],
		"totals": [{"label": _("Total honor"), "value": flt(doc.amount), "strong": True}],
	}


def _student_transfer(doc) -> dict[str, Any]:
	def who(user):
		return (frappe.db.get_value("User", user, "full_name") or user) if user else None

	return {
		"title": _("Mutasi {0}").format(doc.name),
		"subtitle": doc.student_name,
		"status": {"label": doc.status or "-", "variant": "primary"},
		"fields": [
			_f(_("Murid"), f"{doc.student_name} ({doc.student})"),
			_f(_("Cabang asal"), doc.source_company),
			_f(_("Cabang tujuan"), doc.target_company),
			_f(_("Tanggal mutasi"), doc.transfer_date, "date"),
			_f(_("Tahun ajaran tujuan"), doc.target_academic_year),
			_f(_("Program tujuan"), doc.target_program),
			_f(_("Rombel tujuan"), doc.target_student_group),
			_f(_("Alasan"), doc.transfer_reason),
			_f(_("Alasan penolakan"), doc.rejection_reason),
			_f(_("Disetujui cabang asal"), who(doc.source_approver)),
			_f(_("Waktu persetujuan asal"), doc.source_approved_at, "datetime"),
			_f(_("Diterima cabang tujuan"), who(doc.destination_approver)),
			_f(_("Waktu diterima"), doc.destination_accepted_at, "datetime"),
		],
		"tables": [],
	}
