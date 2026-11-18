"""
FAQ / Pusat Bantuan SPI.

Sumber data: DocType inti Frappe ``Help Article`` + ``Help Category``.
(Frappe v16 tidak lagi menyertakan ``Blog Post``; Help Article memang dibuat
untuk knowledge base: judul = pertanyaan, content = jawaban, category = kelompok.)

Konten dikelola Super Administrator lewat Desk (/app/help-article). Hanya artikel
``published = 1`` yang tampil di SPA.

FAQ per role (6 Nov 2026): field ``custom_spi_roles`` (satu Role Profile per baris) membatasi siapa yang melihat
artikel; kosong = semua. Super Administrator melihat semua (beserta target rolenya), kecuali sedang "Lihat sebagai". Seed awal: ``spi_fintoedu.setup.setup_faq``.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr
from frappe.utils.html_utils import sanitize_html

from spi_fintoedu.access import is_super_admin, role_profile
from spi_fintoedu.faq_seed import ROLES_FIELD

MAX_RESULTS = 300


def _require_login() -> None:
	if not frappe.session.user or frappe.session.user == "Guest":
		frappe.throw(_("Anda harus login."), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def list_faqs(search: str | None = None) -> dict[str, Any]:
	"""FAQ terpublikasi, dikelompokkan per kategori. ``search`` mencocokkan pertanyaan & jawaban."""
	_require_login()

	article = frappe.qb.DocType("Help Article")
	has_roles = frappe.get_meta("Help Article").has_field(ROLES_FIELD)
	show_all = is_super_admin()
	my_role = role_profile()
	columns = [article.name, article.title, article.content, article.category]
	if has_roles:
		columns.append(article[ROLES_FIELD])
	query = (
		frappe.qb.from_(article)
		.select(*columns)
		.where(article.published == 1)
		.orderby(article.category)
		.orderby(article.creation)
		.limit(MAX_RESULTS)
	)
	term = cstr(search).strip()
	if term:
		like = f"%{term}%"
		query = query.where((article.title.like(like)) | (article.content.like(like)))
	rows = query.run(as_dict=True)

	def audience(row) -> list[str]:
		raw = (row.get(ROLES_FIELD) or "") if has_roles else ""
		return [r.strip() for r in raw.replace(",", "\n").splitlines() if r.strip()]

	if not show_all:
		rows = [r for r in rows if not audience(r) or (my_role and my_role in audience(r))]

	categories: dict[str, dict[str, Any]] = {}
	for row in rows:
		cat = row.category or _("Umum")
		bucket = categories.setdefault(cat, {"category": cat, "items": []})
		bucket["items"].append(
			{
				"name": row.name,
				"question": row.title,
				"answer": sanitize_html(row.content or ""),
				# target role hanya diperlihatkan ke Super Administrator (untuk memeriksa pembagian FAQ)
				**({"roles": audience(row)} if show_all else {}),
			}
		)

	descriptions = dict(
		frappe.get_all(
			"Help Category",
			filters={"name": ["in", list(categories)]},
			fields=["name", "category_description"],
			as_list=True,
		)
	) if categories else {}
	result = []
	for cat, bucket in categories.items():
		bucket["description"] = descriptions.get(cat) or ""
		result.append(bucket)

	return {"categories": result, "total": len(rows), "search": term}
