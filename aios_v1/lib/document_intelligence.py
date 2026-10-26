"""Read and extract text or tabular rows from a user's private Frappe File."""

import csv
import io
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from aios_v1.lib.error_utils import log_exception, safe_error
from aios_v1.lib.tool_registry import ai_tool, get_tool_context
import frappe

CONVERSATION_DOCTYPE = "AIOS Conversation"

DEFAULT_MAX_ROWS = 200
MAX_ROWS = 1000
MAX_PAGES = 200
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_CHARS = 20000


class DocumentExtractionError(ValueError):
	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.code = code


def _extension(file_name: str, file_url: str = "") -> str:
	name = file_name or urlsplit(file_url or "").path
	return PurePosixPath(unquote(name)).suffix.lower().lstrip(".")


def _unique_columns(header) -> list[str]:
	columns = []
	used = set()
	for index, value in enumerate(header, start=1):
		base = str(value) if value is not None else ""
		base = base if base else f"column_{index}"
		candidate = base
		suffix = 2
		while candidate in used:
			candidate = f"{base}_{suffix}"
			suffix += 1
		used.add(candidate)
		columns.append(candidate)
	return columns


def _bounded_rows(rows, columns: list[str], max_rows: int) -> tuple[list[dict], bool]:
	result = []
	truncated = False
	characters_left = MAX_CHARS
	iterator = iter(rows)
	end = object()
	for _ in range(max_rows):
		row = next(iterator, end)
		if row is end:
			break
		values = list(row)
		if len(values) < len(columns):
			values.extend([""] * (len(columns) - len(values)))
		item = {}
		for column, value in zip(columns, values):
			text = "" if value is None else str(value)
			if len(text) > characters_left:
				item[column] = text[:characters_left]
				characters_left = 0
				truncated = True
				break
			item[column] = value
			characters_left -= len(text)
		result.append(item)
		if characters_left == 0:
			break
	if not truncated:
		if next(iterator, end) is not end:
			truncated = True
	return result, truncated


def _extract_pdf(file_id: str, filename: str, content: bytes, max_pages: int) -> dict:
	from pypdf import PdfReader

	try:
		reader = PdfReader(io.BytesIO(content), strict=False)
		if reader.is_encrypted:
			raise DocumentExtractionError("PDF_ENCRYPTED", "PDF terenkripsi tidak dapat diekstrak.")
		page_count = len(reader.pages)
		page_limit = min(max_pages, MAX_PAGES)
		pages = []
		combined = []
		characters_left = MAX_CHARS
		truncated = page_count > page_limit
		for index in range(min(page_count, page_limit)):
			page_text = (reader.pages[index].extract_text() or "").strip()
			separator = "\n" if combined and page_text else ""
			if len(separator) > characters_left:
				truncated = True
				page_text = ""
				separator = ""
			if len(page_text) + len(separator) > characters_left:
				page_text = page_text[: max(0, characters_left - len(separator))]
				truncated = True
			combined.append(separator + page_text)
			characters_left -= len(separator) + len(page_text)
			pages.append({"page": index + 1, "text": page_text})
			if characters_left == 0 and index + 1 < page_count:
				truncated = True
				break
		text = "".join(combined).strip()
		if not text:
			text = "no extractable text"
		return {
			"file_id": file_id,
			"filename": filename,
			"format": "pdf",
			"pages": pages,
			"content": text,
			"truncated": truncated,
		}
	except DocumentExtractionError:
		raise
	except Exception as exc:
		log_exception("AIOS PDF Extraction", exc=exc)
		raise DocumentExtractionError("INVALID_VALUES", "Isi PDF tidak dapat dibaca.") from exc


def _extract_csv(file_id: str, filename: str, content: bytes, max_rows: int) -> dict:
	text = content.decode("utf-8", errors="replace")
	reader = csv.reader(io.StringIO(text, newline=""), delimiter=",")
	header = next(reader, [])
	columns = _unique_columns(header)
	rows, truncated = _bounded_rows(reader, columns, max_rows)
	return {
		"file_id": file_id,
		"filename": filename,
		"format": "csv",
		"columns": columns,
		"rows": rows,
		"truncated": truncated,
	}


def _extract_xlsx(
	file_id: str, filename: str, content: bytes, max_rows: int, sheet_name: str | None
) -> dict:
	from openpyxl import load_workbook

	try:
		workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
		if sheet_name:
			if sheet_name not in workbook.sheetnames:
				workbook.close()
				raise DocumentExtractionError("SHEET_NOT_FOUND", "Sheet yang diminta tidak ditemukan.")
			worksheet = workbook[sheet_name]
		else:
			worksheet = workbook.active
		rows_iterator = worksheet.iter_rows(values_only=True)
		header = next(rows_iterator, ())
		columns = _unique_columns(header)
		rows, truncated = _bounded_rows(rows_iterator, columns, max_rows)
		workbook.close()
		return {
			"file_id": file_id,
			"filename": filename,
			"format": "xlsx",
			"sheet": worksheet.title,
			"columns": columns,
			"rows": rows,
			"truncated": truncated,
		}
	except DocumentExtractionError:
		raise
	except Exception as exc:
		log_exception("AIOS XLSX Extraction", exc=exc)
		raise DocumentExtractionError("INVALID_VALUES", "Isi XLSX tidak dapat dibaca.") from exc


def extract_document_content(
	file_id: str,
	filename: str,
	file_format: str,
	content: bytes,
	max_rows: int = DEFAULT_MAX_ROWS,
	sheet_name: str | None = None,
) -> dict:
	"""Pure in-memory extraction helper used by the tool and format tests."""
	if file_format == "pdf":
		return _extract_pdf(file_id, filename, content, max_rows)
	if file_format == "csv":
		return _extract_csv(file_id, filename, content, max_rows)
	if file_format == "xlsx":
		return _extract_xlsx(file_id, filename, content, max_rows, sheet_name)
	raise DocumentExtractionError("FORMAT_UNSUPPORTED", "Format file tidak didukung.")


@ai_tool(
	name="document_extract",
	description=(
		"Membaca isi file privat yang dilampirkan pada percakapan aktif; "
		"hanya file milik pengguna dan terikat ke AIOS Conversation yang sama."
	),
	branch=["finance", "sales"],
	roles=[],
	plugin_key="document-intelligence",
	parameters={
		"file_id": {"type": "string", "description": "Nama dokumen File milik pengguna"},
		"format": {
			"type": "string",
			"enum": ["pdf", "csv", "xlsx"],
			"description": "Opsional; harus sama dengan ekstensi file",
			"required": False,
		},
		"sheet_name": {
			"type": "string",
			"description": "Nama sheet XLSX; default sheet aktif",
			"required": False,
		},
		"max_rows": {
			"type": "integer",
			"description": "Jumlah maksimum baris data atau halaman PDF",
			"required": False,
		},
	},
)
def document_extract(file_id, format=None, sheet_name=None, max_rows=DEFAULT_MAX_ROWS):
	if not isinstance(max_rows, int) or isinstance(max_rows, bool) or not 1 <= max_rows <= MAX_ROWS:
		return _file_error("INVALID_VALUES", f"max_rows harus integer 1..{MAX_ROWS}.")
	if not isinstance(file_id, str) or not file_id.strip():
		return _file_error("FILE_FORBIDDEN", "File tidak tersedia untuk pengguna ini.")
	conversation_id = str(get_tool_context().get("conversation_id") or "").strip()
	if not conversation_id:
		return _file_error("CONVERSATION_REQUIRED", "File hanya dapat dibaca dari percakapan yang sama.")

	try:
		file_doc = frappe.get_doc("File", file_id)
	except Exception as exc:
		log_exception("AIOS Document File Lookup", exc=exc)
		return safe_error("File tidak tersedia untuk pengguna ini.", "FILE_FORBIDDEN")

	if int(file_doc.get("is_private") or 0) != 1:
		return _file_error("FILE_NOT_PRIVATE", "Hanya File privat yang dapat dibaca.")
	user = getattr(frappe.session, "user", None)
	if user != "Administrator" and file_doc.owner != user:
		return _file_error("FILE_FORBIDDEN", "File tidak tersedia untuk pengguna ini.")
	attached_to_doctype = file_doc.get("attached_to_doctype")
	attached_to_name = str(file_doc.get("attached_to_name") or "")
	if attached_to_doctype == CONVERSATION_DOCTYPE:
		is_attached_to_conversation = attached_to_name == conversation_id
	elif attached_to_doctype == "AIOS Message":
		message_conversation = frappe.db.get_value("AIOS Message", attached_to_name, "conversation")
		is_attached_to_conversation = str(message_conversation or "") == conversation_id
	else:
		is_attached_to_conversation = False
	if not is_attached_to_conversation:
		return _file_error("FILE_FORBIDDEN", "File tidak terikat ke percakapan ini.")
	try:
		declared_size = int(file_doc.get("file_size") or 0)
	except (TypeError, ValueError) as exc:
		log_exception("AIOS Document File Size", exc=exc)
		declared_size = 0
	if declared_size > MAX_FILE_BYTES:
		return _file_error("FILE_TOO_LARGE", "Ukuran file melebihi batas maksimum.")

	filename = file_doc.get("file_name") or PurePosixPath(urlsplit(file_doc.get("file_url") or "").path).name
	file_format = _extension(filename, file_doc.get("file_url") or "")
	if file_format not in {"pdf", "csv", "xlsx"}:
		return _file_error("FORMAT_UNSUPPORTED", "Format file tidak didukung.")
	if format is not None and (not isinstance(format, str) or format.lower() != file_format):
		return _file_error("FORMAT_MISMATCH", "Format yang diminta tidak cocok dengan ekstensi file.")

	try:
		# An empty encoding list keeps Frappe's File.get_content() result as raw bytes.
		content = file_doc.get_content(encodings=[])
		if isinstance(content, str):
			content = content.encode("utf-8")
		else:
			content = bytes(content)
		if len(content) > MAX_FILE_BYTES:
			return _file_error("FILE_TOO_LARGE", "Ukuran file melebihi batas maksimum.")
		return extract_document_content(file_id, filename, file_format, content, max_rows, sheet_name)
	except DocumentExtractionError as exc:
		log_exception("AIOS Document Extraction", exc=exc, context=exc.code)
		return safe_error(str(exc), exc.code)
	except Exception as exc:
		log_exception("AIOS Document Extraction", exc=exc)
		return safe_error("Dokumen tidak dapat diekstrak.", "INVALID_VALUES")


def _file_error(code: str, message: str) -> dict:
	log_exception("AIOS Document Access", context=code)
	return safe_error(message, code)
