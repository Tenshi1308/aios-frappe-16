"""Telegram channel connector (docs/02 §2.4).

Thin adapter over the existing chat path (`get_manager(branch).handle_stream`).
It never writes to ERPNext: write actions stop at `Pending Action Draft`.
"""

CHANNEL = "telegram"
BRANCH = "sales"
