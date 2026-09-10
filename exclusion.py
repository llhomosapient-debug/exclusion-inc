#!/usr/bin/env python3
"""Exclusion Inc - local AI shell foundation.

Step 1 intentionally has no network access and no model dependency.
The inference backend is a local-only stub that will be replaced by
llama.cpp in the next step.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
AUDIT_FILE = LOG_DIR / "security.audit"
PROTECTED_FILE = ROOT / "config" / "protected.json"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _last_hash() -> str:
    if not AUDIT_FILE.exists():
        return "0" * 64
    try:
        last = AUDIT_FILE.read_text(encoding="utf-8").splitlines()[-1]
        return json.loads(last)["event_hash"]
    except (IndexError, KeyError, json.JSONDecodeError, OSError):
        return "0" * 64


def audit(event_type: str, evidence: str) -> None:
    """Write a local, hash-chained security event.

    Normal conversations are NOT logged. Only security events reach this file.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    previous = _last_hash()
    event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event_type": event_type,
        "evidence_sha256": _hash(evidence),
        "previous_event_hash": previous,
    }
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
    event["event_hash"] = _hash(canonical)
    with AUDIT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, separators=(",", ":")) + "\n")


# These are deliberately narrow indicators of attempts to obtain protected
# configuration/system-prompt material. They are not a general conversation
# surveillance filter.
PROTECTED_PATTERNS = [
    r"(?:show|give|print|reveal|dump|tell)\b.{0,80}(?:system prompt|system message|hidden prompt)",
    r"(?:show|give|read|print|dump)\b.{0,80}(?:protected\.json|secret|credential|private key)",
    r"(?:ignore|bypass|disable)\b.{0,80}(?:security|audit|protection)",
]


def security_check(message: str) -> bool:
    for pattern in PROTECTED_PATTERNS:
        if re.search(pattern, message, flags=re.IGNORECASE | re.DOTALL):
            audit("protected-resource-attempt", message)
            return True
    return False


def generate(message: str) -> str:
    """Temporary local response until the llama.cpp backend is added."""
    if security_check(message):
        return "I can't provide protected system or security configuration."
    return f"[LOCAL ENGINE READY] You said: {message}"


def main() -> None:
    print("\nEXCLUSION INC")
    print("Local AI • Step 1")
    print("Type #endconvo to exit.\n")

    while True:
        try:
            message = input("You > ")
        except (EOFError, KeyboardInterrupt):
            print("\nExclusion Inc stopped.")
            break

        if message.strip().lower() == "#endconvo":
            print("Exclusion Inc stopped.")
            break
        if not message.strip():
            continue

        print(f"AI  > {generate(message)}")


if __name__ == "__main__":
    main()
