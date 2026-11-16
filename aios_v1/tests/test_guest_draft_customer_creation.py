"""Pengujian pembuatan Customer baru otomatis saat approval draf pesanan tamu (Fase 1).

7 skenario wajib:
a. test_approve_draft_creates_new_individual_customer
b. test_approve_draft_creates_new_company_customer
c. test_approve_draft_reuses_existing_customer_by_mobile
d. test_approve_draft_duplicate_name_conflict_handling
e. test_approve_draft_rollback_on_sales_order_failure
f. test_guest_draft_rejects_customer_type_inside_data
g. test_guest_cannot_create_customer_directly

Butuh site + DB: `bench --site aios-v16.localhost run-tests --app aios_v1 --module aios_v1.tests.test_guest_draft_customer_creation`.
"""

import json
import unittest

import frappe
from frappe.utils import nowdate

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore

from aios_v1.lib.draft_manager import approve_and_execute_draft, create_draft, reject_draft
from aios_v1.lib.erpnext_action_drafts import erpnext_action_draft_create
from aios_v1.lib.tool_registry import execute_tool, get_tools_schema_for_worker


def _make_test_user(email: str, first_name: str):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": "Active",
            "roles": [{"role": "AIOS Client"}],
        }
    )
    user.insert(ignore_permissions=True)
    return user


class TestGuestDraftCustomerCreation(IntegrationTestCase):
    USER_EMAIL = "_test.staff.approver@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self.addCleanup(self._restore_and_rollback)

        _make_test_user(self.USER_EMAIL, "_Test Staff Approver")
        frappe.set_user(self.USER_EMAIL)

        self.company = (
            frappe.db.get_single_value("AIOS Setting", "default_company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )

        price_lists = frappe.get_all("Price List", filters={"selling": 1, "enabled": 1}, pluck="name", limit=1)
        self.price_list = price_lists[0] if price_lists else "Standard Selling"

        # Item & warehouse
        non_stock = frappe.get_all("Item", filters={"disabled": 0, "is_stock_item": 0}, pluck="name", limit=1)
        if non_stock:
            self.item_code = non_stock[0]
            self.warehouse = None
        else:
            stock_items = frappe.get_all("Item", filters={"disabled": 0}, pluck="name", limit=1)
            self.item_code = stock_items[0] if stock_items else None
            warehouses = frappe.get_all("Warehouse", filters={"company": self.company, "is_group": 0}, pluck="name", limit=1)
            self.warehouse = warehouses[0] if warehouses else None

        self.created_customers = []

    def _restore_and_rollback(self):
        frappe.set_user("Administrator")
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        frappe.set_user("Administrator")
        for pad in frappe.get_all("Pending Action Draft", filters={"user": self.USER_EMAIL}, pluck="name"):
            frappe.delete_doc("Pending Action Draft", pad, ignore_permissions=True, force=True, delete_permanently=True)

        for c_name in getattr(self, "created_customers", []):
            if frappe.db.exists("Customer", c_name):
                # Hapus Payment Entry terkait
                for pe in frappe.get_all("Payment Entry", filters={"party_type": "Customer", "party": c_name}, pluck="name"):
                    frappe.db.set_value("Payment Entry", pe, "docstatus", 2)
                    frappe.delete_doc("Payment Entry", pe, ignore_permissions=True, force=True)
                # Hapus sales order terkait
                for so in frappe.get_all("Sales Order", filters={"customer": c_name}, pluck="name"):
                    frappe.db.set_value("Sales Order", so, "docstatus", 2)
                    frappe.delete_doc("Sales Order", so, ignore_permissions=True, force=True)
                # Hapus quotation terkait
                for qtn in frappe.get_all("Quotation", filters={"party_name": c_name}, pluck="name"):
                    frappe.db.set_value("Quotation", qtn, "docstatus", 2)
                    frappe.delete_doc("Quotation", qtn, ignore_permissions=True, force=True)
                # Hapus contact
                for c in frappe.get_all("Dynamic Link", filters={"link_doctype": "Customer", "link_name": c_name}, pluck="parent"):
                    frappe.delete_doc("Contact", c, ignore_permissions=True, force=True)
                # Hapus address
                for a in frappe.get_all("Dynamic Link", filters={"link_doctype": "Customer", "link_name": c_name}, pluck="parent"):
                    frappe.delete_doc("Address", a, ignore_permissions=True, force=True)
                frappe.delete_doc("Customer", c_name, ignore_permissions=True, force=True)

        self._restore_and_rollback()

    def _build_order_data(self, customer_placeholder: str) -> dict:
        item = {
            "item_code": self.item_code,
            "qty": 1,
            "rate": 150000,
            "delivery_date": nowdate(),
        }
        if self.warehouse:
            item["warehouse"] = self.warehouse
        return {
            "customer": customer_placeholder,
            "selling_price_list": self.price_list,
            "transaction_date": nowdate(),
            "delivery_date": nowdate(),
            "items": [item],
        }

    def _create_guest_draft(self, customer_placeholder: str, customer_info: dict | None = None):
        data = self._build_order_data(customer_placeholder)
        payload = {
            "doctype": "Sales Order",
            "data": data,
            "reason": "Pesanan tamu baru dari Telegram",
        }
        if customer_info:
            payload["customer_info"] = customer_info

        draft = create_draft(
            task_id="TEST-GUEST-SO-001",
            action_type="CREATE",
            payload=payload,
            branch="sales",
            created_by_agent="sales_manager",
            user=self.USER_EMAIL,
        )
        return draft

    def test_approve_draft_creates_new_individual_customer(self):
        """a. Draf tamu customer_type Individual disetujui staf -> Customer tipe Individual terbuat, Contact terhubung, Sales Order berhasil disubmit (docstatus 1)."""
        cust_name = "_Test Perorangan Baru 1"
        phone = "08129991111"
        self.created_customers.append(cust_name)

        draft = self._create_guest_draft(
            customer_placeholder=cust_name,
            customer_info={
                "customer_type": "Individual",
                "customer_name": cust_name,
                "mobile_no": phone,
                "address": "Jalan Sukabumi No. 10, Bandung",
            },
        )

        result = approve_and_execute_draft(draft.name)
        self.assertTrue(result.get("executed"), f"Approval harus berhasil dieksekusi: {result.get('message')}")
        self.assertEqual(result.get("docstatus"), 1)

        # Verifikasi Customer di ERPNext
        self.assertTrue(frappe.db.exists("Customer", cust_name))
        cust_doc = frappe.get_doc("Customer", cust_name)
        self.assertEqual(cust_doc.customer_type, "Individual")

        # Verifikasi Contact terhubung
        contact_name = frappe.db.sql(
            """
            SELECT parent FROM `tabDynamic Link`
            WHERE link_doctype = 'Customer' AND link_name = %s AND parenttype = 'Contact'
            """,
            (cust_name,),
            pluck=True,
        )
        self.assertTrue(contact_name, "Contact harus terhubung ke Customer baru")

        # Verifikasi Sales Order terbuat dan tersubmit
        so_name = result.get("name") or result.get("document")
        self.assertTrue(frappe.db.exists("Sales Order", so_name))
        so_doc = frappe.get_doc("Sales Order", so_name)
        self.assertEqual(so_doc.customer, cust_name)
        self.assertEqual(so_doc.docstatus, 1)

    def test_approve_draft_creates_new_company_customer(self):
        """b. Draf tamu customer_type Company dengan nama perusahaan dan nama PIC disetujui -> Customer tipe Company terbuat beserta Contact PIC, Sales Order terhubung."""
        corp_name = "_Test PT Maju Bersama"
        pic_name = "Budi Hartono PIC"
        phone = "08129992222"
        self.created_customers.append(corp_name)

        draft = self._create_guest_draft(
            customer_placeholder=corp_name,
            customer_info={
                "customer_type": "Company",
                "customer_name": corp_name,
                "contact_person": pic_name,
                "mobile_no": phone,
                "address": "Kawasan Industri No. 5, Jakarta",
            },
        )

        result = approve_and_execute_draft(draft.name)
        self.assertTrue(result.get("executed"), f"Approval perusahaan harus berhasil: {result.get('message')}")

        # Verifikasi Customer tipe Company
        self.assertTrue(frappe.db.exists("Customer", corp_name))
        cust_doc = frappe.get_doc("Customer", corp_name)
        self.assertEqual(cust_doc.customer_type, "Company")

        # Verifikasi Contact PIC
        contacts = frappe.db.sql(
            """
            SELECT c.name, c.first_name, c.full_name FROM `tabContact` c
            JOIN `tabDynamic Link` dl ON dl.parent = c.name
            WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
            """,
            (corp_name,),
            as_dict=True,
        )
        self.assertTrue(contacts, "Contact harus terhubung ke Company")
        self.assertTrue(any(pic_name in (c.get("full_name") or "") for c in contacts))

    def test_approve_draft_reuses_existing_customer_by_mobile(self):
        """c. Nomor HP sudah terdaftar pada Customer A -> draf baru dengan nomor HP sama -> sistem memakai Customer A dan tidak membuat Customer baru."""
        cust_a_name = "_Test Customer Lama A"
        phone = "08129993333"
        self.created_customers.append(cust_a_name)

        # Buat Customer A dulu secara manual
        cust_a = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": cust_a_name,
                "customer_type": "Individual",
                "customer_group": "Individual",
                "territory": "Indonesia",
            }
        )
        cust_a.insert(ignore_permissions=True)

        from erpnext.selling.doctype.customer.customer import make_contact
        make_contact(
            frappe._dict(
                {
                    "doctype": "Customer",
                    "name": cust_a.name,
                    "customer_name": cust_a_name,
                    "customer_type": "Individual",
                    "mobile_no": phone,
                    "flags": {"ignore_permissions": True},
                }
            )
        )

        initial_customer_count = frappe.db.count("Customer", {"customer_name": ["like", f"{cust_a_name}%"]})
        self.assertEqual(initial_customer_count, 1)

        # Datang pesanan baru dengan nomor HP yang sama tapi nama placeholder sedikit beda
        draft = self._create_guest_draft(
            customer_placeholder="_Test Customer Lama A (Alias)",
            customer_info={
                "customer_type": "Individual",
                "customer_name": "_Test Customer Lama A (Alias)",
                "mobile_no": "+62 812-9993-333",  # variasi format telepon
                "address": "Jalan Dago No. 12",
            },
        )

        result = approve_and_execute_draft(draft.name)
        self.assertTrue(result.get("executed"))

        # Pastikan tidak ada Customer baru yang dibuat (tetap 1)
        final_customer_count = frappe.db.count("Customer", {"customer_name": ["like", f"{cust_a_name}%"]})
        self.assertEqual(final_customer_count, 1, "Tidak boleh membuat Customer baru jika nomor HP sudah ada")

        # Sales Order harus tertaut ke Customer A yang lama
        so = frappe.get_doc("Sales Order", result.get("name") or result.get("document"))
        self.assertEqual(so.customer, cust_a.name)

    def test_approve_draft_duplicate_name_conflict_handling(self):
        """d. Nama sama tapi nomor HP beda -> sistem membuat Customer baru dengan pembeda autoname tanpa bentrok link."""
        common_name = "_Test Nama Kembar"
        phone_1 = "08129994441"
        phone_2 = "08129994442"

        # Buat customer pertama
        cust_1 = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": common_name,
                "customer_type": "Individual",
                "customer_group": "Individual",
                "territory": "Indonesia",
            }
        )
        cust_1.insert(ignore_permissions=True)
        self.created_customers.append(cust_1.name)

        from erpnext.selling.doctype.customer.customer import make_contact
        make_contact(
            frappe._dict(
                {
                    "doctype": "Customer",
                    "name": cust_1.name,
                    "customer_name": common_name,
                    "customer_type": "Individual",
                    "mobile_no": phone_1,
                    "flags": {"ignore_permissions": True},
                }
            )
        )

        # Datang pesanan dengan nama sama tapi HP beda
        draft = self._create_guest_draft(
            customer_placeholder=common_name,
            customer_info={
                "customer_type": "Individual",
                "customer_name": common_name,
                "mobile_no": phone_2,
                "address": "Jalan Riau No. 20, Bandung",
            },
        )

        result = approve_and_execute_draft(draft.name)
        self.assertTrue(result.get("executed"))

        so = frappe.get_doc("Sales Order", result.get("name") or result.get("document"))
        # Customer baru harus dibuat dan namanya berbeda (autoname menambahkan pembeda)
        self.assertNotEqual(so.customer, cust_1.name)
        self.assertTrue(so.customer.startswith(common_name))
        self.created_customers.append(so.customer)

    def test_approve_draft_rollback_on_sales_order_failure(self):
        """e. Simulasikan gagal validasi Sales Order setelah Customer dibuat -> pastikan rollback savepoint membatalkan Customer dan Contact."""
        fail_cust = "_Test Rollback Customer"
        phone = "08129995555"

        # Buat payload dengan item invalid yang pasti gagal saat insert Sales Order
        data = self._build_order_data(fail_cust)
        data["items"] = [{"item_code": "NON_EXISTENT_ITEM_XYZ", "qty": 1, "rate": 100}]
        payload = {
            "doctype": "Sales Order",
            "data": data,
            "reason": "Tes rollback",
            "customer_info": {
                "customer_type": "Individual",
                "customer_name": fail_cust,
                "mobile_no": phone,
                "address": "Jl. Gagal No. 99",
            },
        }

        draft = create_draft(
            task_id="TEST-ROLLBACK-001",
            action_type="CREATE",
            payload=payload,
            branch="sales",
            created_by_agent="sales_manager",
            user=self.USER_EMAIL,
        )

        result = approve_and_execute_draft(draft.name)
        self.assertFalse(result.get("executed"), "Eksekusi harus gagal karena item tidak valid")

        # Customer dan Contact harus ter-rollback (tidak tersimpan di DB)
        self.assertFalse(
            frappe.db.exists("Customer", fail_cust),
            "Customer baru harus dibatalkan saat eksekusi Sales Order gagal (zero orphan data)",
        )

    def test_guest_draft_rejects_customer_type_inside_data(self):
        """f. customer_type di dalam data ditolak saat draf dibuat, sesuai validate_data_fields."""
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.ValidationError):
                erpnext_action_draft_create(
                    action_type="CREATE",
                    doctype="Sales Order",
                    data={
                        "customer": "_Test",
                        "company": self.company,
                        "customer_type": "Individual",  # Dilarang di dalam data!
                        "items": [{"item_code": self.item_code, "qty": 1}],
                        "delivery_date": nowdate(),
                    },
                    reason="Percobaan injeksi field",
                )
        finally:
            frappe.set_user(self.USER_EMAIL)

    def test_guest_cannot_create_customer_directly(self):
        """g. Tamu tidak mendapat tool untuk membuat Customer langsung, pagar guest_allowed tetap hanya 5 tool."""
        # 1. Pagar skema tool worker untuk guest
        guest_schemas = get_tools_schema_for_worker("sales", worker_key="sales_manager", user="Guest")
        guest_tool_names = {s["function"]["name"] for s in guest_schemas}
        self.assertEqual(
            guest_tool_names,
            {"erpnext_doc_list", "erpnext_doc_get", "erpnext_doctype_schema", "erpnext_action_draft_create", "get_current_time"},
            "Pagar tool tamu harus tepat 5 tool yang diizinkan",
        )

        # 2. Pagar eksekusi tool tamu
        frappe.set_user("Guest")
        try:
            # Mencoba eksekusi tool di luar 5 tool tersebut
            res_str = execute_tool("orchestrator_delegate_to_subagent", json.dumps({"target_worker": "finance_manager", "instruction": "Cek"}), context={"user_id": "Guest"})
            res = json.loads(res_str) if isinstance(res_str, str) else res_str
            self.assertIn("error", res)
            self.assertEqual(res.get("code"), "GUEST_TOOL_FORBIDDEN")
        finally:
            frappe.set_user(self.USER_EMAIL)

    def test_contact_failure_fails_execution(self):
        """10.a. Gagal buat Contact menggagalkan eksekusi, draf tetap APPROVED dgn executed False, tanpa Sales Order."""
        cust_name = "_Test Contact Fail Cust"
        self.created_customers.append(cust_name)
        draft = create_draft(
            task_id="test_task_contact_fail",
            action_type="CREATE",
            branch="sales",
            payload={
                "doctype": "Sales Order",
                "data": self._build_order_data(cust_name),
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": cust_name,
                    "mobile_no": "081299990001",
                    "address": "Jalan Percobaan No. 1, Bandung",
                },
            },
            user=self.USER_EMAIL,
        )

        with unittest.mock.patch("erpnext.selling.doctype.customer.customer.make_contact", side_effect=Exception("DB Contact Error")):
            res = approve_and_execute_draft(draft.name)

        self.assertFalse(res["executed"], "Eksekusi harus dilaporkan gagal")
        self.assertEqual(res["draft_status"], "APPROVED")
        self.assertEqual(res.get("code"), "CONTACT_CREATION_FAILED")

        # Pastikan tidak ada Customer maupun Sales Order yang tersimpan (rollback ke savepoint)
        self.assertFalse(frappe.db.exists("Customer", cust_name))
        so_list = frappe.db.get_all("Sales Order", filters={"customer": cust_name})
        self.assertEqual(len(so_list), 0, "Sales Order tidak boleh terbentuk jika kontak gagal")

    def test_delivery_date_from_customer_used(self):
        """10.b. Tanggal kirim dari customer digunakan pada Sales Order, bukan tanggal hari ini."""
        from frappe.utils import add_to_date
        cust_name = "_Test Cust Delivery Date"
        self.created_customers.append(cust_name)
        future_date = add_to_date(nowdate(), days=4)

        order_data = self._build_order_data(cust_name)
        order_data["delivery_date"] = future_date
        for itm in order_data["items"]:
            itm["delivery_date"] = future_date

        draft = create_draft(
            task_id="test_task_delivery_date",
            action_type="CREATE",
            branch="sales",
            payload={
                "doctype": "Sales Order",
                "data": order_data,
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": cust_name,
                    "mobile_no": "081299990002",
                    "address": "Jalan Sukajadi No. 5, Bandung",
                },
            },
            user=self.USER_EMAIL,
        )

        res = approve_and_execute_draft(draft.name)
        self.assertTrue(res["executed"])
        so_name = res["name"]
        so_doc = frappe.get_doc("Sales Order", so_name)
        self.assertEqual(str(so_doc.delivery_date), str(future_date), "Delivery date pada Sales Order harus persis sesuai permintaan customer")
        self.assertNotEqual(str(so_doc.delivery_date), str(add_to_date(nowdate(), days=10)), "Tidak boleh menggunakan default 10 hari ERPNext")

    def test_draft_without_delivery_date_rejected(self):
        """10.c. Draf Sales Order tanpa delivery_date ditolak saat pembuatan."""
        frappe.set_user("Guest")
        try:
            res = erpnext_action_draft_create(
                action_type="CREATE",
                doctype="Sales Order",
                data={
                    "customer": "_Test No Date",
                    "company": self.company,
                    "items": [{"item_code": self.item_code, "qty": 1}],
                    # delivery_date sengaja tidak diisi!
                },
                reason="Pemesanan tanpa tanggal kirim",
                customer_info={
                    "customer_type": "Individual",
                    "customer_name": "_Test No Date",
                    "mobile_no": "081299990003",
                    "address": "Jalan Dago No. 1, Bandung",
                },
            )
            self.assertIn("error", res)
            self.assertEqual(res.get("code"), "DELIVERY_DATE_REQUIRED")
        finally:
            frappe.set_user(self.USER_EMAIL)

    def test_reject_approved_failed_draft(self):
        """10.d. Draf berstatus APPROVED yang gagal eksekusi dapat di-reject staf dengan alasan."""
        cust_name = "_Test Reject Approved Cust"
        self.created_customers.append(cust_name)
        draft = create_draft(
            task_id="test_task_reject_approved",
            action_type="CREATE",
            branch="sales",
            payload={
                "doctype": "Sales Order",
                "data": self._build_order_data(cust_name),
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": cust_name,
                    "mobile_no": "081299990004",
                    "address": "Jalan Tanpa Kota",  # Alamat tanpa kota memicu gagal eksekusi
                },
            },
            user=self.USER_EMAIL,
        )

        # Approve pertama kali gagal karena kota tidak ditemukan
        res = approve_and_execute_draft(draft.name)
        self.assertFalse(res["executed"])
        self.assertEqual(res["draft_status"], "APPROVED")

        # Staf menolak draf yang berstatus APPROVED tersebut
        rej_res = reject_draft(draft.name, reason="Alamat tidak memuat nama kota yang valid")
        self.assertEqual(rej_res["status"], "success")

        draft.reload()
        self.assertEqual(draft.status, "REJECTED")
        self.assertEqual(draft.rejection_reason, "Alamat tidak memuat nama kota yang valid")

    def test_proactive_notification_sent_to_guest_chat(self):
        """10.e. Notifikasi proaktif dikirim via Telegram ke chat_id pelanggan saat draf ditolak atau gagal approve."""
        test_chat_id = "8999777123"
        draft = create_draft(
            task_id="test_task_proactive_notif",
            action_type="CREATE",
            branch="sales",
            payload={
                "doctype": "Sales Order",
                "source_telegram_chat_id": test_chat_id,
                "data": self._build_order_data("_Test Proactive"),
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": "_Test Proactive",
                    "mobile_no": "081299990005",
                    "address": "Jalan Cihampelas No. 10, Bandung",
                },
            },
            user=self.USER_EMAIL,
        )

        # 1. Uji notifikasi saat draf ditolak staf
        sent_messages = []
        with unittest.mock.patch("aios_v1.lib.connector.telegram_client.send_message", side_effect=lambda cid, txt: sent_messages.append((cid, txt)) or True):
            reject_draft(draft.name, reason="Nomor HP tidak dapat dihubungi")

        self.assertEqual(len(sent_messages), 1, "Pesan Telegram harus terkirim saat reject")
        self.assertEqual(str(sent_messages[0][0]), test_chat_id)
        self.assertIn("Nomor HP tidak dapat dihubungi", sent_messages[0][1])
        self.assertIn("Anda tidak perlu mengulang", sent_messages[0][1])
        # Tegaskan pesan proaktif saat reject draf TIDAK mengandung karakter emoji
        import re
        emoji_pattern = re.compile(r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]")
        self.assertFalse(bool(emoji_pattern.search(sent_messages[0][1])), "Pesan proaktif saat reject draf tidak boleh memuat emoji")
        self.assertNotIn("🙏", sent_messages[0][1])

        # 2. Uji notifikasi saat approve gagal eksekusi
        draft_fail = create_draft(
            task_id="test_task_proactive_fail",
            action_type="CREATE",
            branch="sales",
            payload={
                "doctype": "Sales Order",
                "source_telegram_chat_id": test_chat_id,
                "data": self._build_order_data("_Test Proactive Fail"),
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": "_Test Proactive Fail",
                    "mobile_no": "081299990006",
                    "address": "Alamat Tanpa Kota",
                },
            },
            user=self.USER_EMAIL,
        )

        sent_fail_messages = []
        with unittest.mock.patch("aios_v1.lib.connector.telegram_client.send_message", side_effect=lambda cid, txt: sent_fail_messages.append((cid, txt)) or True):
            approve_and_execute_draft(draft_fail.name)

        self.assertEqual(len(sent_fail_messages), 1, "Pesan Telegram harus terkirim saat approve gagal")
        self.assertEqual(str(sent_fail_messages[0][0]), test_chat_id)
        self.assertIn("Kota pada alamat pengiriman tidak ditemukan", sent_fail_messages[0][1])
        # Tegaskan pesan proaktif saat approve gagal TIDAK mengandung karakter emoji
        self.assertFalse(bool(emoji_pattern.search(sent_fail_messages[0][1])), "Pesan proaktif saat approve gagal tidak boleh memuat emoji")
        self.assertNotIn("🙏", sent_fail_messages[0][1])

    def test_contact_name_not_duplicated(self):
        """10.f. Kontak primer yang dibuat untuk nama lengkap tidak mengalami duplikasi nama (first/middle/last rapi)."""
        cust_name = "_Test Budi Uji Live"
        self.created_customers.append(cust_name)
        draft = create_draft(
            task_id="test_task_contact_name",
            action_type="CREATE",
            branch="sales",
            payload={
                "doctype": "Sales Order",
                "data": self._build_order_data(cust_name),
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": cust_name,
                    "mobile_no": "081299990007",
                    "address": "Jalan Merdeka No. 1, Bandung",
                },
            },
            user=self.USER_EMAIL,
        )

        res = approve_and_execute_draft(draft.name)
        self.assertTrue(res["executed"])

        # Periksa Contact
        contact_name = frappe.db.get_value("Customer", cust_name, "customer_primary_contact")
        self.assertTrue(contact_name, "customer_primary_contact harus terisi")
        contact_doc = frappe.get_doc("Contact", contact_name)

        self.assertEqual(contact_doc.first_name, "_Test")
        self.assertEqual(contact_doc.middle_name, "Budi Uji")
        self.assertEqual(contact_doc.last_name, "Live")
        self.assertEqual(contact_doc.full_name, "_Test Budi Uji Live", "full_name Contact tidak boleh ganda")

    def test_retry_approved_failed_draft(self):
        """10.g. Draf berstatus APPROVED yang gagal eksekusi dapat dicoba lagi (retry) dan berhasil setelah penyebab diperbaiki."""
        cust_name = "_Test Retry Cust"
        self.created_customers.append(cust_name)
        draft = create_draft(
            task_id="test_task_retry",
            action_type="CREATE",
            branch="sales",
            payload={
                "doctype": "Sales Order",
                "data": self._build_order_data(cust_name),
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": cust_name,
                    "mobile_no": "081299990008",
                    "address": "Jalan Pasteur No. 10, Bandung",
                },
            },
            user=self.USER_EMAIL,
        )

        # 1. Eksekusi pertama gagal karena simulasi error
        with unittest.mock.patch("erpnext.selling.doctype.customer.customer.make_contact", side_effect=Exception("Simulated transient error")):
            res1 = approve_and_execute_draft(draft.name)

        self.assertFalse(res1["executed"])
        self.assertEqual(res1["draft_status"], "APPROVED")

        # 2. Eksekusi kedua (retry) tanpa error harus berhasil
        res2 = approve_and_execute_draft(draft.name)
        self.assertTrue(res2["executed"], "Retry draft APPROVED harus berhasil")
        self.assertEqual(res2["draft_status"], "EXECUTED")
        self.assertTrue(frappe.db.exists("Customer", cust_name))
        self.assertTrue(frappe.db.exists("Sales Order", res2["name"]))

    def test_proactive_notification_sent_on_approve_success(self):
        """Fase 1: Notifikasi proaktif dikirim ke Telegram saat draf Sales Order berhasil di-approve (EXECUTED) dan mode_of_payment Cash terisi."""
        import re
        emoji_pattern = re.compile(r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]")
        test_chat_id = "8999777201"
        cust_name = "_Test Approve Success Notif"
        self.created_customers.append(cust_name)

        order_data = self._build_order_data(cust_name)
        draft = create_draft(
            task_id="test_task_approve_success_notif",
            action_type="CREATE",
            branch="sales",
            payload={
                "doctype": "Sales Order",
                "source_telegram_chat_id": test_chat_id,
                "data": order_data,
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": cust_name,
                    "mobile_no": "081299990011",
                    "address": "Jalan Asia Afrika No. 8, Bandung",
                    "payment_method": "Cash",
                },
            },
            user=self.USER_EMAIL,
        )

        sent_messages = []
        with unittest.mock.patch(
            "aios_v1.lib.connector.telegram_client.send_message",
            side_effect=lambda cid, txt: sent_messages.append((cid, txt)) or True,
        ):
            res = approve_and_execute_draft(draft.name)

        self.assertTrue(res.get("executed"))
        self.assertEqual(res.get("draft_status"), "EXECUTED")
        so_name = res.get("name") or res.get("document")
        self.assertTrue(so_name)

        so_doc = frappe.get_doc("Sales Order", so_name)
        self.assertTrue(so_doc.payment_schedule, "Sales Order harus memiliki payment_schedule")
        self.assertEqual(so_doc.payment_schedule[0].mode_of_payment, "Cash")

        self.assertEqual(len(sent_messages), 1, "Pesan Telegram harus dikirim tepat 1 kali saat approve sukses")
        self.assertEqual(str(sent_messages[0][0]), test_chat_id)
        msg_text = sent_messages[0][1]
        self.assertNotIn(so_name, msg_text, "Pesan customer tidak boleh memuat nomor Sales Order")
        self.assertNotIn("SAL-ORD", msg_text, "Pesan customer tidak boleh memuat nomor internal SO")
        self.assertNotIn("ACC-PAY", msg_text, "Pesan customer tidak boleh memuat nomor internal Payment Entry")
        self.assertNotIn("Sales Order", msg_text, "Pesan customer tidak boleh memuat label internal Sales Order")
        self.assertIn("Pesanan Anda telah disetujui.", msg_text)
        self.assertIn(str(so_doc.delivery_date), msg_text, "Pesan harus memuat tanggal pengiriman")
        self.assertTrue("150.000" in msg_text or "150,000" in msg_text, f"Pesan harus memuat harga dasar terformat: {msg_text}")
        self.assertTrue("16.500" in msg_text or "16,500" in msg_text, f"Pesan harus memuat PPN 11% terformat: {msg_text}")
        self.assertTrue("166.500" in msg_text or "166,500" in msg_text, f"Pesan harus memuat total termasuk PPN terformat: {msg_text}")
        self.assertNotIn("(belum termasuk pajak/PPN)", msg_text)
        self.assertIn("Cash (Tunai)", msg_text, "Pesan harus memuat info pembayaran Cash (Tunai)")
        self.assertIn("ditahan", msg_text, "Pesan harus memuat info pengiriman ditahan bila belum dibayar")
        self.assertFalse(bool(emoji_pattern.search(msg_text)), "Pesan notifikasi approve sukses tidak boleh memuat emoji")

        # Nomor Sales Order tetap tersimpan di result & payload draf untuk staf
        self.assertEqual(res.get("document"), so_name)
        draft.reload()
        saved_result = json.loads(draft.payload or "{}").get("result", {})
        self.assertEqual(saved_result.get("document"), so_name)

    def test_approve_success_notification_idempotent_on_retry(self):
        """Fase 1: Pemanggilan ulang approve_and_execute_draft pada draf yang sudah EXECUTED tidak mengirim notifikasi dua kali."""
        test_chat_id = "8999777202"
        cust_name = "_Test Approve Idempotent Notif"
        self.created_customers.append(cust_name)

        draft = create_draft(
            task_id="test_task_approve_idempotent_notif",
            action_type="CREATE",
            branch="sales",
            payload={
                "doctype": "Sales Order",
                "source_telegram_chat_id": test_chat_id,
                "data": self._build_order_data(cust_name),
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": cust_name,
                    "mobile_no": "081299990012",
                    "address": "Jalan Braga No. 15, Bandung",
                    "payment_method": "Cash",
                },
            },
            user=self.USER_EMAIL,
        )

        sent_messages = []
        with unittest.mock.patch(
            "aios_v1.lib.connector.telegram_client.send_message",
            side_effect=lambda cid, txt: sent_messages.append((cid, txt)) or True,
        ):
            res1 = approve_and_execute_draft(draft.name)
            res2 = approve_and_execute_draft(draft.name)

        self.assertTrue(res1.get("executed"))
        self.assertEqual(res1.get("document"), res2.get("document"))
        self.assertEqual(len(sent_messages), 1, "Retry pada draf EXECUTED tidak boleh mengirim notifikasi kedua")

    def test_guest_draft_requires_cash_payment_method(self):
        """Fase 1: Draf Sales Order tamu wajib menyertakan payment_method 'Cash' di customer_info; selain Cash ditolak."""
        frappe.set_user("Guest")
        try:
            # 1. Tanpa payment_method -> PAYMENT_METHOD_REQUIRED
            res_missing = erpnext_action_draft_create(
                action_type="CREATE",
                doctype="Sales Order",
                data={
                    "customer": "_Test Payment Method",
                    "company": self.company,
                    "items": [{"item_code": self.item_code, "qty": 1}],
                    "delivery_date": nowdate(),
                },
                reason="Tes tanpa metode bayar",
                customer_info={
                    "customer_type": "Individual",
                    "customer_name": "_Test Payment Method",
                    "mobile_no": "081299990013",
                    "address": "Jalan Setiabudi No. 10, Bandung",
                },
            )
            self.assertIn("error", res_missing)
            self.assertEqual(res_missing.get("code"), "PAYMENT_METHOD_REQUIRED")

            # 2. Metode bayar di luar Cash (misal QRIS / Transfer) -> UNSUPPORTED_PAYMENT_METHOD
            res_qris = erpnext_action_draft_create(
                action_type="CREATE",
                doctype="Sales Order",
                data={
                    "customer": "_Test Payment Method",
                    "company": self.company,
                    "items": [{"item_code": self.item_code, "qty": 1}],
                    "delivery_date": nowdate(),
                },
                reason="Tes metode bayar QRIS",
                customer_info={
                    "customer_type": "Individual",
                    "customer_name": "_Test Payment Method",
                    "mobile_no": "081299990013",
                    "address": "Jalan Setiabudi No. 10, Bandung",
                    "payment_method": "QRIS",
                },
            )
            self.assertIn("error", res_qris)
            self.assertEqual(res_qris.get("code"), "UNSUPPORTED_PAYMENT_METHOD")

            # 3. Metode bayar Cash -> berhasil disimpan
            with unittest.mock.patch("aios_v1.lib.connector.notify.get_channel_recipients", return_value=[self.USER_EMAIL]):
                res_cash = erpnext_action_draft_create(
                    action_type="CREATE",
                    doctype="Sales Order",
                    data={
                        "customer": "_Test Payment Method",
                        "company": self.company,
                        "items": [{"item_code": self.item_code, "qty": 1}],
                        "delivery_date": nowdate(),
                    },
                    reason="Tes metode bayar Cash",
                    customer_info={
                        "customer_type": "Individual",
                        "customer_name": "_Test Payment Method",
                        "mobile_no": "081299990013",
                        "address": "Jalan Setiabudi No. 10, Bandung",
                        "payment_method": "Cash",
                    },
                )
            self.assertEqual(res_cash.get("status"), "PENDING_APPROVAL")
            saved_payload = json.loads(frappe.db.get_value("Pending Action Draft", res_cash["draft_id"], "payload") or "{}")
            self.assertEqual(saved_payload.get("customer_info", {}).get("payment_method"), "Cash")
        finally:
            frappe.set_user(self.USER_EMAIL)

    def test_confirm_cash_payment_creates_payment_entry_and_updates_so(self):
        """Fase 1 (Jalan B): Tombol konfirmasi bayar staf membuat Payment Entry (Receive, Cash), update advance_paid SO, kirim notifikasi ke customer, dan idempotent."""
        import re

        from aios_v1.lib.draft_manager import confirm_draft_cash_payment

        emoji_pattern = re.compile(r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]")

        test_chat_id = "8999777204"
        cust_name = "_Test Confirm Cash Payment"
        self.created_customers.append(cust_name)

        draft = create_draft(
            task_id="test_task_confirm_cash_payment",
            action_type="CREATE",
            branch="sales",
            payload={
                "doctype": "Sales Order",
                "source_telegram_chat_id": test_chat_id,
                "data": self._build_order_data(cust_name),
                "customer_info": {
                    "customer_type": "Individual",
                    "customer_name": cust_name,
                    "mobile_no": "081299990014",
                    "address": "Jalan Buah Batu No. 25, Bandung",
                    "payment_method": "Cash",
                },
            },
            user=self.USER_EMAIL,
        )

        with unittest.mock.patch("aios_v1.lib.connector.telegram_client.send_message", return_value=True):
            exec_res = approve_and_execute_draft(draft.name)
        self.assertTrue(exec_res.get("executed"))
        so_name = exec_res["name"]

        # 1. Tamu tidak boleh memanggil confirm_draft_cash_payment
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.PermissionError):
                confirm_draft_cash_payment(draft.name)
        finally:
            frappe.set_user(self.USER_EMAIL)

        # 2. Staf pemilik mengonfirmasi pembayaran Cash (klik pertama)
        payment_msgs = []
        with unittest.mock.patch(
            "aios_v1.lib.connector.telegram_client.send_message",
            side_effect=lambda cid, txt: payment_msgs.append((cid, txt)) or True,
        ):
            pay_res1 = confirm_draft_cash_payment(draft.name)
            # 3. Klik kedua harus idempotent (tidak membuat Payment Entry baru dan tidak kirim notifikasi ganda)
            pay_res2 = confirm_draft_cash_payment(draft.name)

        self.assertEqual(pay_res1.get("status"), "success")
        pe_name = pay_res1.get("payment_entry")
        self.assertTrue(pe_name, "Harus mengembalikan nama Payment Entry")
        self.assertEqual(pay_res2.get("payment_entry"), pe_name, "Klik kedua harus mengembalikan Payment Entry yang sama")

        pe_doc = frappe.get_doc("Payment Entry", pe_name)
        self.assertEqual(pe_doc.docstatus, 1)
        self.assertEqual(pe_doc.payment_type, "Receive")
        self.assertEqual(pe_doc.mode_of_payment, "Cash")
        self.assertEqual(pe_doc.owner, self.USER_EMAIL)
        self.assertEqual(pe_doc.modified_by, self.USER_EMAIL)

        # Pastikan hanya ada 1 Payment Entry untuk Sales Order ini
        pe_refs = frappe.get_all(
            "Payment Entry Reference",
            filters={"reference_doctype": "Sales Order", "reference_name": so_name, "docstatus": 1},
            pluck="parent",
        )
        self.assertEqual(len(pe_refs), 1, "Tidak boleh ada Payment Entry ganda")

        # Sales Order advance_paid harus terupdate penuh dan audit atribusi staf
        so_doc = frappe.get_doc("Sales Order", so_name)
        self.assertEqual(float(so_doc.advance_paid or 0), float(so_doc.grand_total))
        self.assertEqual(so_doc.owner, self.USER_EMAIL)
        self.assertEqual(so_doc.modified_by, self.USER_EMAIL)

        # Notifikasi pembayaran diterima terkirim tepat 1 kali ke customer tanpa emoji dan tanpa nomor internal
        self.assertEqual(len(payment_msgs), 1, "Notifikasi pembayaran diterima hanya dikirim 1 kali")
        self.assertEqual(str(payment_msgs[0][0]), test_chat_id)
        paid_msg = payment_msgs[0][1]
        self.assertNotIn(so_name, paid_msg, "Pesan customer tidak boleh memuat nomor Sales Order")
        self.assertNotIn(pe_name, paid_msg, "Pesan customer tidak boleh memuat nomor Payment Entry")
        self.assertNotIn("SAL-ORD", paid_msg, "Pesan customer tidak boleh memuat nomor internal SO")
        self.assertNotIn("ACC-PAY", paid_msg, "Pesan customer tidak boleh memuat nomor internal Payment Entry")
        self.assertNotIn("Sales Order", paid_msg, "Pesan customer tidak boleh memuat label internal Sales Order")
        self.assertIn("Pembayaran Cash Anda sebesar", paid_msg)
        self.assertTrue("166.500" in paid_msg or "166,500" in paid_msg, f"Pesan harus memuat nominal bayar terformat (termasuk PPN 11%): {paid_msg}")
        self.assertIn(str(so_doc.delivery_date), paid_msg, "Pesan harus memuat tanggal pengiriman")
        self.assertIn("Cash", paid_msg)
        self.assertFalse(bool(emoji_pattern.search(paid_msg)), "Notifikasi pembayaran tidak boleh memuat emoji")

        # Nomor SO dan Payment Entry tetap ada di dict result dan payload draf untuk staf
        self.assertEqual(pay_res1.get("sales_order"), so_name)
        self.assertEqual(pay_res1.get("payment_entry"), pe_name)
        draft.reload()
        saved_result = json.loads(draft.payload or "{}").get("result", {})
        self.assertEqual(saved_result.get("document"), so_name)
        self.assertEqual(saved_result.get("payment_entry"), pe_name)

    def test_guest_sales_order_draft_applies_ppn_11_and_matches_erpnext_grand_total(self):
        """Guest Sales Order draft menerapkan Sales Taxes and Charges Template PPN 11% dan total cocok dengan grand_total ERPNext."""
        from aios_v1.lib.erpnext_action_drafts import _build_draft_summary, _format_confirmation_message

        cust_name = "_Test Guest SO PPN 11"
        self.created_customers.append(cust_name)
        item_payload = {"item_code": self.item_code, "qty": 1, "rate": 850000, "delivery_date": nowdate()}
        if self.warehouse:
            item_payload["warehouse"] = self.warehouse

        frappe.set_user("Guest")
        try:
            with unittest.mock.patch("aios_v1.lib.connector.notify.get_channel_recipients", return_value=[self.USER_EMAIL]):
                draft_res = erpnext_action_draft_create(
                    action_type="CREATE",
                    doctype="Sales Order",
                    data={
                        "customer": cust_name,
                        "selling_price_list": self.price_list,
                        "delivery_date": nowdate(),
                        "items": [item_payload],
                    },
                    reason="Uji PPN 11% Sales Order tamu",
                    customer_info={
                        "customer_type": "Individual",
                        "customer_name": cust_name,
                        "mobile_no": "081299990021",
                        "address": "Jalan Merdeka No. 10, Bandung",
                        "payment_method": "Cash",
                    },
                )
        finally:
            frappe.set_user(self.USER_EMAIL)

        self.assertEqual(draft_res.get("status"), "PENDING_APPROVAL")
        self.assertTrue(draft_res.get("taxes_and_charges"))
        self.assertEqual(draft_res.get("base_total"), 850000.0)
        self.assertEqual(draft_res.get("tax_amount"), 93500.0)
        self.assertEqual(draft_res.get("total"), 943500.0)
        self.assertEqual(draft_res.get("formatted_base_total"), "Rp 850.000")
        self.assertEqual(draft_res.get("formatted_tax_amount"), "Rp 93.500")
        self.assertEqual(draft_res.get("formatted_total"), "Rp 943.500")

        draft_doc = frappe.get_doc("Pending Action Draft", draft_res["draft_id"])
        summary = _build_draft_summary(draft_doc, json.loads(draft_doc.payload or "{}"), action="approve")
        confirm_msg = _format_confirmation_message("approve", summary)
        self.assertIn("Harga Dasar: Rp 850.000", confirm_msg)
        self.assertIn("PPN 11%: Rp 93.500", confirm_msg)
        self.assertIn("Total: Rp 943.500", confirm_msg)
        self.assertNotIn("(belum termasuk pajak/PPN)", confirm_msg)

        exec_res = approve_and_execute_draft(draft_res["draft_id"])
        self.assertTrue(exec_res.get("executed"), exec_res.get("message"))
        so_doc = frappe.get_doc("Sales Order", exec_res["document"])
        self.assertEqual(so_doc.docstatus, 1)
        self.assertEqual(so_doc.taxes_and_charges, draft_res["taxes_and_charges"])
        self.assertEqual(float(so_doc.net_total), 850000.0)
        self.assertEqual(float(so_doc.total_taxes_and_charges), 93500.0)
        self.assertEqual(float(so_doc.grand_total), 943500.0)
        self.assertEqual(float(draft_res["total"]), float(so_doc.rounded_total or so_doc.grand_total))

    def test_guest_quotation_draft_maps_customer_and_applies_ppn_11_matching_erpnext_grand_total(self):
        """Guest Quotation draft memperbaiki mapping party_name + quotation_to='Customer', menerapkan PPN 11%, dan total cocok dengan grand_total ERPNext."""
        from aios_v1.lib.erpnext_action_drafts import _build_draft_summary, _format_confirmation_message

        cust_name = "_Test Guest Quotation PPN 11"
        self.created_customers.append(cust_name)
        item_payload = {"item_code": self.item_code, "qty": 2, "rate": 850000}

        frappe.set_user("Guest")
        try:
            with unittest.mock.patch("aios_v1.lib.connector.notify.get_channel_recipients", return_value=[self.USER_EMAIL]):
                draft_res = erpnext_action_draft_create(
                    action_type="CREATE",
                    doctype="Quotation",
                    data={
                        "customer": cust_name,
                        "selling_price_list": self.price_list,
                        "items": [item_payload],
                    },
                    reason="Permintaan penawaran harga tamu dengan PPN 11%",
                    customer_info={
                        "customer_type": "Company",
                        "customer_name": cust_name,
                        "contact_person": "Andi Saputra",
                        "mobile_no": "081299990022",
                        "address": "Jalan Gatot Subroto No. 22, Jakarta",
                    },
                )
        finally:
            frappe.set_user(self.USER_EMAIL)

        self.assertEqual(draft_res.get("status"), "PENDING_APPROVAL")
        self.assertEqual(draft_res.get("doctype"), "Quotation")
        self.assertTrue(draft_res.get("taxes_and_charges"))
        self.assertEqual(draft_res.get("base_total"), 1700000.0)
        self.assertEqual(draft_res.get("tax_amount"), 187000.0)
        self.assertEqual(draft_res.get("total"), 1887000.0)
        self.assertEqual(draft_res.get("formatted_base_total"), "Rp 1.700.000")
        self.assertEqual(draft_res.get("formatted_tax_amount"), "Rp 187.000")
        self.assertEqual(draft_res.get("formatted_total"), "Rp 1.887.000")

        draft_doc = frappe.get_doc("Pending Action Draft", draft_res["draft_id"])
        saved_data = json.loads(draft_doc.payload or "{}").get("data", {})
        self.assertNotIn("customer", saved_data)
        self.assertEqual(saved_data.get("quotation_to"), "Customer")
        self.assertEqual(saved_data.get("party_name"), cust_name)

        summary = _build_draft_summary(draft_doc, json.loads(draft_doc.payload or "{}"), action="approve")
        confirm_msg = _format_confirmation_message("approve", summary)
        self.assertIn("Harga Dasar: Rp 1.700.000", confirm_msg)
        self.assertIn("PPN 11%: Rp 187.000", confirm_msg)
        self.assertIn("Total: Rp 1.887.000", confirm_msg)
        self.assertNotIn("(belum termasuk pajak/PPN)", confirm_msg)

        exec_res = approve_and_execute_draft(draft_res["draft_id"])
        self.assertTrue(exec_res.get("executed"), exec_res.get("message"))
        qtn_doc = frappe.get_doc("Quotation", exec_res["document"])
        self.assertEqual(qtn_doc.docstatus, 1)
        self.assertEqual(qtn_doc.quotation_to, "Customer")
        self.assertEqual(qtn_doc.party_name, cust_name)
        self.assertEqual(qtn_doc.taxes_and_charges, draft_res["taxes_and_charges"])
        self.assertEqual(float(qtn_doc.net_total), 1700000.0)
        self.assertEqual(float(qtn_doc.total_taxes_and_charges), 187000.0)
        self.assertEqual(float(qtn_doc.grand_total), 1887000.0)
        self.assertEqual(float(draft_res["total"]), float(qtn_doc.rounded_total or qtn_doc.grand_total))

    def test_guest_interim_summary_single_confirmation_and_draft_creation_flow(self):
        """Alur multi-turn tamu: katalog Item Price menyuplai pratinjau PPN 11%, satu ringkasan lengkap sebelum konfirmasi, lalu draf dibuat dengan total ERPNext identik."""
        from aios_v1.managers import get_manager
        from aios_v1.shared.guest_persona import GUEST_ACTIVE_DIRECTIVE

        cust_name = "_Test Guest Flow 3 Baris"
        self.created_customers.append(cust_name)
        sales_mgr = get_manager("sales")
        conv_id = sales_mgr.ensure_conversation("Guest", force_new=True)

        temp_ip_created = None
        orig_ip_rate = None
        existing_ip = frappe.db.get_value(
            "Item Price",
            {"item_code": self.item_code, "price_list": "Standard Selling", "selling": 1},
            "name",
        )
        if existing_ip:
            orig_ip_rate = frappe.db.get_value("Item Price", existing_ip, "price_list_rate")
            frappe.db.set_value("Item Price", existing_ip, "price_list_rate", 850000)
            ip_name = existing_ip
        else:
            ip_doc = frappe.get_doc(
                {
                    "doctype": "Item Price",
                    "item_code": self.item_code,
                    "price_list": "Standard Selling",
                    "selling": 1,
                    "currency": "IDR",
                    "price_list_rate": 850000,
                }
            ).insert(ignore_permissions=True)
            ip_name = ip_doc.name
            temp_ip_created = ip_name

        captured_prompts: list[str] = []
        observed_tool_results: list[dict] = []
        created_draft_ids: list[str] = []
        turn_idx = {"n": 0}
        tool_round = {"n": 0}

        def scripted_chat(messages, usage=None, tools=None, tool_calls=None):
            if usage is not None:
                usage.update(prompt_tokens=10, completion_tokens=10, total_tokens=20)
            if messages[0]["role"] == "system" and (not captured_prompts or tool_round["n"] == 0):
                sys_blob = "\n".join(m["content"] for m in messages if m.get("role") == "system")
                captured_prompts.append(sys_blob)

            # Turn 1: guest asks catalog + orders 1 pcs -> call erpnext_doc_list("Item Price") -> show interim 3-line breakdown
            if turn_idx["n"] == 0:
                if tool_round["n"] == 0:
                    tool_round["n"] += 1
                    tool_calls.append(
                        {
                            "id": "call_catalog_1",
                            "type": "function",
                            "function": {
                                "name": "erpnext_doc_list",
                                "arguments": json.dumps(
                                    {"doctype": "Item Price", "filters": {"item_code": self.item_code}}
                                ),
                            },
                        }
                    )
                    return iter(["Sebentar saya cek katalog resmi ya."])
                ip_tool_payload = json.loads(messages[-1]["content"])
                observed_tool_results.append(ip_tool_payload)
                row = ip_tool_payload["data"][0]
                item_label = row.get("item_name") or self.item_code
                return iter(
                    [
                        "\n## 📝 Rincian Pesanan Sementara\n"
                        f"• {item_label} (1 unit)\n"
                        f"Harga Dasar: {row['formatted_base_rate']}\n"
                        f"PPN 11%: {row['formatted_ppn_11_per_unit']}\n"
                        f"Total: {row['formatted_rate_with_ppn_11']}\n"
                        "Atas nama Perorangan atau Perusahaan?"
                    ]
                )

            # Turn 2: guest sends complete details -> single Ringkasan Pemesanan + 1x confirmation (no draft tool yet)
            if turn_idx["n"] == 1:
                row = observed_tool_results[0]["data"][0]
                item_label = row.get("item_name") or self.item_code
                return iter(
                    [
                        "## 📝 Ringkasan Pemesanan\n"
                        f"• {item_label} x1\n"
                        f"Harga Dasar: {row['formatted_base_rate']}\n"
                        f"PPN 11%: {row['formatted_ppn_11_per_unit']}\n"
                        f"Total: {row['formatted_rate_with_ppn_11']}\n"
                        f"Pemesan: {cust_name} (081299990055)\n"
                        "Alamat: Jalan Merdeka No. 50, Bandung\n"
                        f"Tanggal Pengiriman: {nowdate()}\n"
                        "Pembayaran: Cash (Tunai) sebelum barang dikirim.\n"
                        "Apakah ringkasan dan ketentuan pembayaran Cash di atas sudah sesuai?"
                    ]
                )

            # Turn 3: guest confirms once -> immediately call erpnext_action_draft_create
            if tool_round["n"] == 0:
                tool_round["n"] += 1
                item_arg = {"item_code": self.item_code, "qty": 1, "rate": 850000, "delivery_date": nowdate()}
                if self.warehouse:
                    item_arg["warehouse"] = self.warehouse
                tool_calls.append(
                    {
                        "id": "call_draft_1",
                        "type": "function",
                        "function": {
                            "name": "erpnext_action_draft_create",
                            "arguments": json.dumps(
                                {
                                    "action_type": "CREATE",
                                    "doctype": "Sales Order",
                                    "data": {
                                        "customer": cust_name,
                                        "selling_price_list": "Standard Selling",
                                        "delivery_date": nowdate(),
                                        "items": [item_arg],
                                    },
                                    "reason": "Pesanan uji alur 3 baris PPN",
                                    "customer_info": {
                                        "customer_type": "Individual",
                                        "customer_name": cust_name,
                                        "mobile_no": "081299990055",
                                        "address": "Jalan Merdeka No. 50, Bandung",
                                        "payment_method": "Cash",
                                    },
                                }
                            ),
                        },
                    }
                )
                return iter(["Baik, saya buatkan draf pesanannya."])

            draft_tool_payload = json.loads(messages[-1]["content"])
            observed_tool_results.append(draft_tool_payload)
            if draft_tool_payload.get("draft_id"):
                created_draft_ids.append(draft_tool_payload["draft_id"])
            return iter(
                [
                    f"\nNomor Draf: {draft_tool_payload['draft_id']}\n"
                    f"Harga Dasar: {draft_tool_payload['formatted_base_total']}\n"
                    f"PPN 11%: {draft_tool_payload['formatted_tax_amount']}\n"
                    f"Total: {draft_tool_payload['formatted_total']}"
                ]
            )

        try:
            with (
                unittest.mock.patch("aios_v1.managers.base_manager.chat_stream", side_effect=scripted_chat),
                unittest.mock.patch("aios_v1.managers.base_manager.record_token_usage_batch"),
                unittest.mock.patch("aios_v1.lib.connector.notify.get_channel_recipients", return_value=[self.USER_EMAIL]),
                unittest.mock.patch("aios_v1.lib.tool_registry._plugin_enabled", return_value=True),
                unittest.mock.patch("aios_v1.lib.tool_registry._plugin_scope_allows", return_value=True),
            ):
                frappe.set_user("Guest")

                # Turn 1
                turn_idx["n"] = 0
                tool_round["n"] = 0
                list(sales_mgr.handle_stream("Saya mau pesan 1 pcs", conversation_id=conv_id, user="Guest"))

                # Turn 2
                turn_idx["n"] = 1
                tool_round["n"] = 0
                list(
                    sales_mgr.handle_stream(
                        f"Perorangan, nama {cust_name}, 081299990055, Jalan Merdeka No. 50 Bandung, kirim hari ini",
                        conversation_id=conv_id,
                        user="Guest",
                    )
                )
                # Before confirmation, no draft created yet
                self.assertEqual(len(created_draft_ids), 0)

                # Turn 3 (single confirmation)
                turn_idx["n"] = 2
                tool_round["n"] = 0
                list(sales_mgr.handle_stream("Ya, setuju Cash, buatkan drafnya", conversation_id=conv_id, user="Guest"))

            # Verify prompt enforcement across turns
            self.assertEqual(len(captured_prompts), 3)
            self.assertIn(GUEST_ACTIVE_DIRECTIVE, captured_prompts[-1])
            self.assertIn("minta satu kali konfirmasi saja sebelum membuat draf", captured_prompts[0])
            self.assertNotIn("(belum termasuk pajak/PPN)", captured_prompts[0])

            # Verify Item Price enrichment & Draft match ERPNext calculation
            self.assertEqual(len(observed_tool_results), 2)
            ip_row = observed_tool_results[0]["data"][0]
            self.assertEqual(ip_row["base_rate"], 850000.0)
            self.assertEqual(ip_row["ppn_11_per_unit"], 93500.0)
            self.assertEqual(ip_row["rate_with_ppn_11"], 943500.0)
            self.assertEqual(ip_row["formatted_base_rate"], "Rp 850.000")
            self.assertEqual(ip_row["formatted_ppn_11_per_unit"], "Rp 93.500")
            self.assertEqual(ip_row["formatted_rate_with_ppn_11"], "Rp 943.500")

            draft_tool_res = observed_tool_results[1]
            self.assertEqual(draft_tool_res["base_total"], 850000.0)
            self.assertEqual(draft_tool_res["tax_amount"], 93500.0)
            self.assertEqual(draft_tool_res["total"], 943500.0)

            # Stored assistant messages show 3 lines on interim and final, no old disclaimer
            msgs = frappe.get_all(
                "AIOS Message",
                filters={"conversation": str(conv_id), "role": "manager"},
                fields=["content"],
                order_by="creation asc",
            )
            self.assertEqual(len(msgs), 3)
            for m in msgs:
                self.assertIn("Harga Dasar: Rp 850.000", m.content)
                self.assertIn("PPN 11%: Rp 93.500", m.content)
                self.assertIn("Total: Rp 943.500", m.content)
                self.assertNotIn("(belum termasuk pajak/PPN)", m.content)

            # Approve created draft and verify grand_total matches
            frappe.set_user(self.USER_EMAIL)
            self.assertEqual(len(created_draft_ids), 1)
            exec_res = approve_and_execute_draft(created_draft_ids[0])
            self.assertTrue(exec_res.get("executed"), exec_res.get("message"))
            so_doc = frappe.get_doc("Sales Order", exec_res["document"])
            self.assertEqual(float(so_doc.rounded_total or so_doc.grand_total), 943500.0)
        finally:
            frappe.set_user("Administrator")
            if temp_ip_created and frappe.db.exists("Item Price", temp_ip_created):
                frappe.delete_doc("Item Price", temp_ip_created, ignore_permissions=True, force=True, delete_permanently=True)
            elif existing_ip and orig_ip_rate is not None:
                frappe.db.set_value("Item Price", existing_ip, "price_list_rate", orig_ip_rate)
            for msg_name in frappe.get_all("AIOS Message", filters={"conversation": str(conv_id)}, pluck="name"):
                frappe.delete_doc("AIOS Message", msg_name, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("AIOS Conversation", str(conv_id)):
                frappe.delete_doc("AIOS Conversation", str(conv_id), ignore_permissions=True, force=True, delete_permanently=True)
