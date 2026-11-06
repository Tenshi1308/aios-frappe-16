# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AIOSChannelThread(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        channel: DF.Data
        conversation: DF.Link
        display_name: DF.Data | None
        external_thread_id: DF.Data
        last_inbound_at: DF.Datetime | None
        last_outbound_at: DF.Datetime | None
        party: DF.DynamicLink | None
        party_type: DF.Literal["", "Contact", "Customer", "Lead"]
        status: DF.Literal["Open", "Closed"]
        username: DF.Data | None
    # end: auto-generated types

    _DOCTYPE_NAME = "AIOS Channel Thread"
