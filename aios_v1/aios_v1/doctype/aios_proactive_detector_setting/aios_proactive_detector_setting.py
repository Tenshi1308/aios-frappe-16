# Copyright (c) 2026, AIOS V1 and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AIOSProactiveDetectorSetting(Document):
    """Single DocType: jadwal tiap detektor proaktif Sales, diatur dari Desk."""

    def validate(self):
        seen = set()
        for row in self.get("detectors") or []:
            key = str(row.detector_key or "").strip()
            if not key:
                frappe.throw("Setiap baris jadwal wajib memilih detektor.")
            if key in seen:
                frappe.throw(f"Detektor {key} muncul lebih dari sekali.")
            seen.add(key)
            hour = int(row.run_hour or 0)
            if hour < 0 or hour > 23:
                frappe.throw(f"Jam jalan untuk {key} harus antara 0 dan 23.")
            if str(row.frequency or "").lower() == "weekly" and not str(row.day_of_week or "").strip():
                frappe.throw(f"Detektor {key} berjadwal mingguan tetapi hari belum dipilih.")
