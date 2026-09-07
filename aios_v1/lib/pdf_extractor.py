"""
aios_v1.lib.pdf_extractor

Modul utilitas untuk mengekstrak teks dari dokumen PDF.
Menggunakan 'pypdf' sebagai jalur utama (cepat, ~10ms).
Jika dokumen tidak memiliki teks digital (hasil scan / gambar),
modul otomatis beralih ke Tesseract OCR (ind+eng).
"""

import io
import logging
from typing import Dict, Any

import pytesseract
from pdf2image import convert_from_bytes
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes, filename: str = "document.pdf") -> Dict[str, Any]:
    """
    Mengekstrak teks dari raw bytes file PDF secara cerdas.
    """
    if not file_bytes:
        return {
            "success": False,
            "filename": filename,
            "pages": 0,
            "text": "",
            "is_ocr": False,
            "error": "File PDF kosong atau tidak ditemukan"
        }

    # Potong ke boundary byte PDF jika file diawali multipart header
    if not file_bytes.startswith(b"%PDF"):
        pdf_start = file_bytes.find(b"%PDF")
        if pdf_start != -1:
            pdf_end = file_bytes.rfind(b"%%EOF")
            if pdf_end != -1:
                file_bytes = file_bytes[pdf_start:pdf_end + 5]
            else:
                file_bytes = file_bytes[pdf_start:]

    # 1. Jalur Utama: Ekstraksi Digital Cepat via pypdf
    pages_text = []
    total_pages = 1

    try:
        reader = PdfReader(io.BytesIO(file_bytes), strict=False)
        total_pages = len(reader.pages)

        for idx, page in enumerate(reader.pages):
            try:
                page_content = page.extract_text() or ""
            except Exception:
                page_content = ""

            if page_content.strip():
                pages_text.append(f"--- [Halaman {idx + 1}] ---\n{page_content.strip()}")

    except Exception as e:
        logger.warning(f"pypdf gagal membaca {filename}: {e}")

    full_text = "\n\n".join(pages_text).strip()

    # Jika teks digital ditemukan, langsung kembalikan
    if full_text:
        return {
            "success": True,
            "filename": filename,
            "pages": total_pages,
            "text": full_text,
            "is_ocr": False
        }

    # 2. Jalur Fallback: OCR Berbasis Gambar via Tesseract (ind+eng)
    try:
        images = convert_from_bytes(file_bytes)
        if images:
            total_pages = len(images)
            ocr_pages = []

            for idx, img in enumerate(images):
                try:
                    ocr_text = pytesseract.image_to_string(img, lang="ind+eng")
                except Exception as ocr_err:
                    logger.warning(f"OCR gagal pada halaman {idx + 1} file {filename}: {ocr_err}")
                    ocr_text = ""

                if ocr_text.strip():
                    ocr_pages.append(f"--- [Halaman {idx + 1} (Hasil Scan OCR)] ---\n{ocr_text.strip()}")

            full_ocr_text = "\n\n".join(ocr_pages).strip()

            if full_ocr_text:
                return {
                    "success": True,
                    "filename": filename,
                    "pages": total_pages,
                    "text": full_ocr_text,
                    "is_ocr": True
                }

    except Exception as e:
        logger.error(f"Fallback OCR gagal pada {filename}: {e}")

    # 3. Jika dokumen scan kosong atau tidak dapat dikenali
    empty_notice = (
        f"Dokumen PDF '{filename}' ({total_pages} halaman) berhasil dipindai, "
        f"namun tidak ditemukan teks yang dapat dibaca."
    )

    return {
        "success": True,
        "filename": filename,
        "pages": total_pages,
        "text": empty_notice,
        "is_ocr": False
    }
