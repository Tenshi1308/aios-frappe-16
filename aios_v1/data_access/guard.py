"""Guard untuk koneksi database eksternal dari input klien (N5/S12).

Modul ini murni stdlib supaya bisa diuji tanpa frappe.
"""

import ipaddress
import os
import socket

ALLOWED_DB_PORTS = {3306, 5432}


def _resolved_ips(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"Host tidak dapat di-resolve: {host}") from exc
    return sorted({info[4][0] for info in infos})


def is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_external_db_config(
    engine: str,
    config: dict,
    sqlite_root: str | None = None,
) -> None:
    """Tolak konfigurasi DB eksternal yang mengarah ke jaringan privat atau path liar."""
    engine = (engine or "").lower()

    if engine == "sqlite":
        path = str(config.get("path") or config.get("file_path") or "").strip()
        if not path:
            raise ValueError("Path database SQLite wajib diisi")
        if ".." in path.replace("\\", "/").split("/"):
            raise ValueError("Path database tidak boleh mengandung '..'")
        if not sqlite_root:
            raise ValueError("Direktori database SQLite belum dikonfigurasi")
        resolved = os.path.realpath(os.path.expanduser(path))
        root = os.path.realpath(sqlite_root)
        if os.path.commonpath([resolved, root]) != root:
            raise ValueError("Path database SQLite harus berada di direktori data AIOS")
        return

    if engine in ("mysql", "mariadb", "postgres", "postgresql"):
        host = str(config.get("host") or "").strip()
        if not host:
            raise ValueError("Host database wajib diisi")
        port = int(config.get("port") or (3306 if engine in ("mysql", "mariadb") else 5432))
        if port not in ALLOWED_DB_PORTS:
            raise ValueError(f"Port database tidak diizinkan: {port}")
        # ponytail: resolusi DNS sekali di sini; DNS rebinding belum ditutup.
        # Upgrade: pin IP hasil resolusi ke koneksi adapter.
        for ip in _resolved_ips(host, port):
            if not is_public_ip(ip):
                raise ValueError("Host database tidak boleh mengarah ke IP privat/loopback")
        return

    raise ValueError(f"Engine database tidak didukung: {engine}")
