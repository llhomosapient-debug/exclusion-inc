from __future__ import annotations

import re


PROTECTED_PATTERNS = [
    re.compile(r"(?:show|give|print|reveal|dump|tell)\b.{0,100}(?:system prompt|system message|hidden prompt)", re.I | re.S),
    re.compile(r"(?:show|give|read|print|dump)\b.{0,100}(?:protected\.json|secret|credential|private key)", re.I | re.S),
    re.compile(r"(?:ignore|bypass|disable)\b.{0,100}(?:security|audit|protection)", re.I | re.S),
]


def protected_action_attempt(message: str) -> bool:
    return any(pattern.search(message) for pattern in PROTECTED_PATTERNS)
