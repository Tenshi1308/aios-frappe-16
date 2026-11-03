# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AIOSConversationFlag(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        closed_at: DF.Datetime | None
        closed_by: DF.Link | None
        closing_note: DF.SmallText | None
        conversation: DF.Link | None
        excerpt: DF.SmallText | None
        label: DF.Data | None
        message_ids: DF.SmallText | None
        owner_user: DF.Link
        reason_text: DF.SmallText | None
        rule_key: DF.Data
        severity: DF.Literal["low", "medium", "high"]
        status: DF.Literal["Open", "Closed"]
        thread: DF.Link
    # end: auto-generated types

    _DOCTYPE_NAME = "AIOS Conversation Flag"

    def validate(self):
        # Closing is a human act: record who and when, and never let a save
        # silently reopen or fabricate a closure.
        if self.status == "Closed":
            if not self.closed_by:
                self.closed_by = frappe.session.user
            if not self.closed_at:
                self.closed_at = now_datetime()
        else:
            self.closed_by = None
            self.closed_at = None
