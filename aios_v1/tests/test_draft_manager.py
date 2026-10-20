import unittest
import frappe
from frappe.utils import add_to_date, now_datetime
from aios_v1.lib.draft_manager import expire_old_drafts, approve_draft, reject_draft

@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestDraftManager(unittest.TestCase):
    
    def setUp(self):
        # Create a fresh test draft
        self.doc = frappe.get_doc({
            "doctype": "Pending Action Draft",
            "task_id": "TEST-TASK-001",
            "type": "create_po",
            "payload": '{"item": "Baut"}',
            "status": "PENDING_APPROVAL",
            # Set expires_at in the past
            "expires_at": add_to_date(now_datetime(), hours=-2)
        })
        self.doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
    def tearDown(self):
        # Cleanup
        if frappe.db.exists("Pending Action Draft", self.doc.name):
            frappe.delete_doc("Pending Action Draft", self.doc.name, ignore_permissions=True)
        frappe.db.commit()
        
    def test_expire_old_drafts(self):
        # The document was created with an expired date
        self.assertEqual(frappe.db.get_value("Pending Action Draft", self.doc.name, "status"), "PENDING_APPROVAL")
        
        # Run cron job manually
        expire_old_drafts()
        
        # Check if status changed to EXPIRED
        new_status = frappe.db.get_value("Pending Action Draft", self.doc.name, "status")
        self.assertEqual(new_status, "EXPIRED")

    def test_approve_draft(self):
        # Reset to pending and future expiry
        self.doc.status = "PENDING_APPROVAL"
        self.doc.expires_at = add_to_date(now_datetime(), hours=2)
        self.doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        res = approve_draft(self.doc.name)
        self.assertEqual(res["status"], "success")
        
        new_status = frappe.db.get_value("Pending Action Draft", self.doc.name, "status")
        self.assertEqual(new_status, "APPROVED")

    def test_reject_draft(self):
        # Reset to pending and future expiry
        self.doc.status = "PENDING_APPROVAL"
        self.doc.expires_at = add_to_date(now_datetime(), hours=2)
        self.doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        res = reject_draft(self.doc.name)
        self.assertEqual(res["status"], "success")
        
        new_status = frappe.db.get_value("Pending Action Draft", self.doc.name, "status")
        self.assertEqual(new_status, "REJECTED")

    def test_cannot_approve_non_pending(self):
        # Set to expired
        self.doc.status = "EXPIRED"
        self.doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        with self.assertRaises(frappe.exceptions.ValidationError):
            approve_draft(self.doc.name)
