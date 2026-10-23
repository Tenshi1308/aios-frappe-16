"""Deterministic finance calculations for AIOS workers."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from aios_v1.lib.error_utils import log_exception, safe_error
from aios_v1.lib.tool_registry import ai_tool

TWO_PLACES = Decimal("0.01")
OPERATIONS = frozenset({"margin", "growth", "tax", "reconcile", "projection"})
MIN_PROJECTION_PERIODS = 1
MAX_PROJECTION_PERIODS = 120
PERCENT_MULTIPLIER = Decimal("100")
MIN_TAX_RATE = Decimal("0")
MAX_TAX_RATE = Decimal("1")


def _failure(code: str, message: str) -> dict:
	log_exception("AIOS Quant Calculator", context=code)
	return safe_error(message, code)


def _number(value, label: str) -> Decimal:
	if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
		raise ValueError(label)
	try:
		result = Decimal(str(value))
	except (InvalidOperation, ValueError, TypeError) as exc:
		raise ValueError(label) from exc
	if not result.is_finite():
		raise ArithmeticError(label)
	return result


def _money(value: Decimal) -> str:
	return format(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), ".2f")


@ai_tool(
	name="quant_calculate",
	description="Menghitung margin, pertumbuhan, pajak, rekonsiliasi, atau proyeksi linear secara deterministik.",
	branch=["finance", "sales"],
	roles=[],
	plugin_key="quant-calculator",
	parameters={
		"operation": {
			"type": "string",
			"enum": sorted(OPERATIONS),
			"description": "Operasi: margin, growth, tax, reconcile, projection",
		},
		"values": {"type": "object", "description": "Nilai numerik yang diperlukan oleh operasi"},
		"rate": {
			"type": "number",
			"description": "Tarif pajak sebagai fraksi 0..1; wajib untuk tax",
			"required": False,
		},
	},
)
def quant_calculate(operation, values, rate=None):
	if not isinstance(operation, str) or operation not in OPERATIONS:
		return _failure("INVALID_OPERATION", "Operasi kalkulator tidak dikenal.")
	if not isinstance(values, dict):
		return _failure("INVALID_VALUES", "values harus berupa object numerik.")

	required = {
		"margin": ("revenue", "cost"),
		"growth": ("current", "previous"),
		"tax": ("amount",),
		"reconcile": ("expected", "actual"),
		"projection": ("opening", "net_change", "periods"),
	}[operation]
	if any(key not in values for key in required):
		return _failure("INVALID_VALUES", "values tidak memuat semua nilai yang diperlukan.")

	try:
		if operation == "projection":
			periods = values["periods"]
			if isinstance(periods, bool) or not isinstance(periods, int):
				return _failure(
					"PERIODS_OUT_OF_RANGE",
					f"periods harus integer {MIN_PROJECTION_PERIODS}..{MAX_PROJECTION_PERIODS}.",
				)
			if not MIN_PROJECTION_PERIODS <= periods <= MAX_PROJECTION_PERIODS:
				return _failure(
					"PERIODS_OUT_OF_RANGE",
					f"periods harus integer {MIN_PROJECTION_PERIODS}..{MAX_PROJECTION_PERIODS}.",
				)
			opening = _number(values["opening"], "opening")
			net_change = _number(values["net_change"], "net_change")
			return {
				"opening": _money(opening),
				"net_change": _money(net_change),
				"periods": periods,
				"balances": [_money(opening + net_change * period) for period in range(1, periods + 1)],
			}

		numbers = {key: _number(values[key], key) for key in required}
	except ArithmeticError as exc:
		log_exception("AIOS Quant Calculator", exc=exc)
		return _failure("NON_FINITE", "Semua nilai harus berupa angka hingga.")
	except ValueError as exc:
		log_exception("AIOS Quant Calculator", exc=exc)
		return _failure("INVALID_VALUES", "values harus memuat angka yang valid.")

	try:
		if operation == "margin":
			revenue = numbers["revenue"]
			if revenue <= 0:
				return _failure("REVENUE_NOT_POSITIVE", "revenue harus lebih besar dari 0.")
			gross_margin = revenue - numbers["cost"]
			return {
				"gross_margin": _money(gross_margin),
				"margin_percent": _money(gross_margin / revenue * PERCENT_MULTIPLIER),
			}
		if operation == "growth":
			previous = numbers["previous"]
			if previous <= 0:
				return _failure("PREVIOUS_NOT_POSITIVE", "previous harus lebih besar dari 0.")
			absolute = numbers["current"] - previous
			return {
				"absolute": _money(absolute),
				"percent": _money(absolute / previous * PERCENT_MULTIPLIER),
			}
		if operation == "tax":
			if rate is None or isinstance(rate, bool):
				return _failure("INVALID_RATE", "rate wajib berupa fraksi 0..1.")
			try:
				tax_rate = Decimal(str(rate))
			except (InvalidOperation, ValueError, TypeError) as exc:
				log_exception("AIOS Quant Calculator", exc=exc)
				return _failure("INVALID_RATE", "rate wajib berupa fraksi 0..1.")
			if not tax_rate.is_finite():
				return _failure("NON_FINITE", "Semua nilai harus berupa angka hingga.")
			if not MIN_TAX_RATE <= tax_rate <= MAX_TAX_RATE:
				return _failure("INVALID_RATE", "rate harus berada di antara 0 dan 1.")
			tax = numbers["amount"] * tax_rate
			return {"tax": _money(tax), "total": _money(numbers["amount"] + tax)}
		if operation == "reconcile":
			difference = numbers["actual"] - numbers["expected"]
			return {
				"difference": _money(difference),
				"status": "MATCH" if difference == 0 else "MISMATCH",
			}
	except (ArithmeticError, InvalidOperation, OverflowError) as exc:
		log_exception("AIOS Quant Calculation Failed", exc=exc)
		return safe_error("Perhitungan tidak dapat diselesaikan.", "INVALID_VALUES")

	return _failure("INVALID_OPERATION", "Operasi kalkulator tidak dikenal.")
