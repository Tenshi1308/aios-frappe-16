"""Long-poll supervisor for the Telegram channel.

Why not `scheduler_events`: Frappe's scheduler sleeps until the next multiple of
`DEFAULT_SCHEDULER_TICK` (240 s), so even a per-minute cron runs every ~4
minutes — too slow for customer chat. This is a managed long-poll process
instead (docs/02 §2.4, decision log docs/05.1 §6).

Run it under the bench supervisor:

    bench --site <site> execute aios_v1.lib.connector.poller.run_forever

The offset lives in `AIOS Telegram Setting.poll_offset` (durable). The redis
cache used by the old implementation had `save ""` + `allkeys-lru`, so a restart
could replay updates and duplicate documents.
"""

from __future__ import annotations

import signal
import time

import frappe

from aios_v1.lib.connector import telegram_client
from aios_v1.lib.connector.dispatch import process_update
from aios_v1.lib.error_utils import log_exception

SETTING_DOCTYPE = "AIOS Telegram Setting"
POLL_TIMEOUT = telegram_client.POLL_TIMEOUT
IDLE_SLEEP = 1
ERROR_SLEEP = 3

_STOP = False


def _handle_signal(signum, frame):
    global _STOP
    _STOP = True


def _offset() -> int:
    return int(frappe.db.get_single_value(SETTING_DOCTYPE, "poll_offset") or 0)


def _store_offset(value: int) -> None:
    """Persist the last processed update id before acknowledging the next batch."""
    frappe.db.set_value(SETTING_DOCTYPE, SETTING_DOCTYPE, "poll_offset", int(value), update_modified=False)
    frappe.db.commit()


def poll_once() -> int:
    """Fetch and process one batch. Returns how many updates were handled.

    Safe to call from tests and from a cron as a watchdog: it never loops.
    """
    if not telegram_client.is_configured():
        return 0

    try:
        updates = telegram_client.get_updates(offset=_offset() + 1 if _offset() else 0)
    except telegram_client.ConnectorError as exc:
        log_exception("AIOS Connector Poll", context=exc.code)
        return 0

    processed = 0
    for update in updates:
        update_id = update.get("update_id")
        try:
            process_update(update)
            processed += 1
        except Exception as exc:
            # One bad update must not kill the batch; log and keep the offset
            # moving so the same payload is not retried forever.
            log_exception("AIOS Connector Update", exc=exc, context=str(update_id))
        if isinstance(update_id, int):
            _store_offset(update_id)
    return processed


def run_forever() -> None:
    """Blocking loop for the managed process. Stops cleanly on SIGTERM/SIGINT."""
    global _STOP
    _STOP = False
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if not telegram_client.is_configured():
        log_exception("AIOS Connector Start", context="token/aktif belum diisi; poller tidak jalan")
        return

    try:
        telegram_client.delete_webhook()
    except telegram_client.ConnectorError as exc:
        log_exception("AIOS Connector Webhook Reset", context=exc.code)

    while not _STOP:
        try:
            handled = poll_once()
        except Exception as exc:
            log_exception("AIOS Connector Loop", exc=exc)
            time.sleep(ERROR_SLEEP)
            continue
        if not handled:
            time.sleep(IDLE_SLEEP)

    log_exception("AIOS Connector Stop", context="poller berhenti")
