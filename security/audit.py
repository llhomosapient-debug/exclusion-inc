from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class AuditLog:
    """Local tamper-evident security-event log.

    Only security events are written. Normal chat messages are not logged.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _previous_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        try:
            last = self.path.read_text(encoding="utf-8").splitlines()[-1]
            return json.loads(last)["event_hash"]
        except (IndexError, KeyError, json.JSONDecodeError, OSError):
            return "0" * 64

    def record(self, event_type: str, evidence: str) -> None:
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event_type": event_type,
            "evidence_sha256": self._sha256(evidence),
            "previous_event_hash": self._previous_hash(),
        }
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
        event["event_hash"] = self._sha256(canonical)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, separators=(",", ":")) + "\n")
