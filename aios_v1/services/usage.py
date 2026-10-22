"""Akuntansi token (L8, docs/04 Alur 4).

PoC memakai satu gerbang kuota: `AIOS Setting.site_token_limit` dibandingkan
dengan `site_tokens_used`. `User.aios_tokens_used` hanya statistik harian,
bukan gerbang per user.
"""

import frappe

SITE_DOCTYPE = "AIOS Setting"
SITE_USED_FIELD = "site_tokens_used"


def check_site_token_quota() -> bool:
	"""True bila masih ada sisa kuota site; False bila plafon sudah terpakai."""
	# ponytail: cek-lalu-jalan, bukan reservasi atomik; request bersamaan bisa
	# overshoot sedikit. Upgrade ke reservasi atomik kalau plafon harus keras.
	limit = frappe.db.get_single_value(SITE_DOCTYPE, "site_token_limit") or 0
	used = frappe.db.get_single_value(SITE_DOCTYPE, SITE_USED_FIELD) or 0
	return not (limit and used >= limit)


def _increment_site_counter(delta: int) -> None:
	"""Update atomik counter site di `tabSingles` (tanpa `doc.save()`)."""
	frappe.db.sql(
		"INSERT INTO `tabSingles` (doctype, field, value) "
		"SELECT %s, %s, 0 WHERE NOT EXISTS ("
		"SELECT 1 FROM `tabSingles` WHERE doctype = %s AND field = %s)",
		(SITE_DOCTYPE, SITE_USED_FIELD, SITE_DOCTYPE, SITE_USED_FIELD),
	)
	frappe.db.sql(
		"UPDATE `tabSingles` SET value = COALESCE(NULLIF(value, ''), 0) + %s "
		"WHERE doctype = %s AND field = %s",
		(delta, SITE_DOCTYPE, SITE_USED_FIELD),
	)


def record_token_usage(
	user: str,
	provider: str,
	model: str,
	branch: str,
	agent: str,
	input_tokens: int = 0,
	output_tokens: int = 0,
	total_tokens: int | None = None,
	cost: float = 0.0,
) -> dict:
	"""Catat detail pemakaian + update counter site/user secara atomik."""
	input_tokens = max(0, int(input_tokens or 0))
	output_tokens = max(0, int(output_tokens or 0))
	total_tokens = max(0, int(total_tokens if total_tokens is not None else input_tokens + output_tokens))

	frappe.get_doc(
		{
			"doctype": "AIOS Token Usage",
			"user": user,
			"provider": provider or "",
			"model": model or "",
			"branch": branch or "",
			"agent": agent or "",
			"input_tokens": input_tokens,
			"output_tokens": output_tokens,
			"total_tokens": total_tokens,
			"cost": cost,
		}
	).insert(ignore_permissions=True)

	_increment_site_counter(total_tokens)
	frappe.db.sql(
		"UPDATE `tabUser` SET aios_tokens_used = COALESCE(aios_tokens_used, 0) + %s WHERE name = %s",
		(total_tokens, user),
	)
	return {"total_tokens": total_tokens}


def reset_daily_counters() -> None:
	"""Job harian: nol-kan counter site + statistik per user; ledger tetap utuh."""
	frappe.db.sql(
		"UPDATE `tabSingles` SET value = 0 WHERE doctype = %s AND field = %s",
		(SITE_DOCTYPE, SITE_USED_FIELD),
	)
	frappe.db.sql("UPDATE `tabUser` SET aios_tokens_used = 0 WHERE COALESCE(aios_tokens_used, 0) <> 0")
