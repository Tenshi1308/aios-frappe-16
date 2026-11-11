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
        self.assertIn(so_name, msg_text, "Pesan harus memuat nomor Sales Order")
        self.assertIn(str(so_doc.delivery_date), msg_text, "Pesan harus memuat tanggal pengiriman")
        self.assertTrue("150.000" in msg_text or "150,000" in msg_text, f"Pesan harus memuat total terformat: {msg_text}")
        self.assertTrue("Cash" in msg_text or "Tunai" in msg_text, "Pesan harus memuat info pembayaran Cash/Tunai")
        self.assertFalse(bool(emoji_pattern.search(msg_text)), "Pesan notifikasi approve sukses tidak boleh memuat emoji")

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

        # Pastikan hanya ada 1 Payment Entry untuk Sales Order ini
        pe_refs = frappe.get_all(
            "Payment Entry Reference",
            filters={"reference_doctype": "Sales Order", "reference_name": so_name, "docstatus": 1},
            pluck="parent",
        )
        self.assertEqual(len(pe_refs), 1, "Tidak boleh ada Payment Entry ganda")

        # Sales Order advance_paid harus terupdate penuh
        so_doc = frappe.get_doc("Sales Order", so_name)
        self.assertEqual(float(so_doc.advance_paid or 0), float(so_doc.grand_total))

        # Notifikasi pembayaran diterima terkirim tepat 1 kali ke customer tanpa emoji
        self.assertEqual(len(payment_msgs), 1, "Notifikasi pembayaran diterima hanya dikirim 1 kali")
        self.assertEqual(str(payment_msgs[0][0]), test_chat_id)
        self.assertIn(so_name, payment_msgs[0][1])
        self.assertIn(pe_name, payment_msgs[0][1])
        self.assertFalse(bool(emoji_pattern.search(payment_msgs[0][1])), "Notifikasi pembayaran tidak boleh memuat emoji")
