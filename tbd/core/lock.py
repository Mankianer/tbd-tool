"""Sperrdatei, damit das Tool nicht gleichzeitig auf zwei Rechnern im selben Vault läuft."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime
from pathlib import Path


class VaultLockedError(RuntimeError):
    pass


class VaultLock:
    """Verwendung:  with VaultLock(tool_dir): ..."""

    FILE_NAME = "lock"

    def __init__(self, tool_dir: Path, force: bool = False):
        self.path = tool_dir / self.FILE_NAME
        self.force = force

    def __enter__(self) -> "VaultLock":
        if self.path.exists() and not self.force:
            try:
                info = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                info = {}
            raise VaultLockedError(
                f"Der Vault ist gesperrt (Rechner: {info.get('host', '?')}, seit {info.get('since', '?')}).\n"
                f"Läuft das Tool gerade woanders oder ist die Synchronisation noch nicht fertig?\n"
                f"Wenn ein früherer Lauf abgestürzt ist: mit --force erneut starten "
                f"oder {self.path} löschen.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "since": datetime.now().isoformat(timespec="seconds"),
        }), encoding="utf-8")
        return self

    def __exit__(self, *exc) -> None:
        self.path.unlink(missing_ok=True)
