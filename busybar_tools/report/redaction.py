from __future__ import annotations

import re
from typing import List

SENSITIVE_KEY_EXACT = {
    "authorization",
    "bssid",
    "email",
    "manual_code",
    "password",
    "pin",
    "qr_code",
    "ssid",
}

SENSITIVE_KEY_PARTS = (
    "api-token",
    "api_token",
    "access_key",
    "certificate",
    "private",
    "pubkey",
    "secret",
    "_mac",
    "token",
)

MASK = "<redacted>"

ANSI_RE = re.compile(
    r"(?:\x1B[@-Z\\-_]|\x1B\[[0-?]*[ -/]*[@-~]|\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)|\x1B[P^_].*?\x1B\\)",
    re.DOTALL,
)


def is_sensitive_key(key: str) -> bool:
    key_l = key.lower()
    if key_l in SENSITIVE_KEY_EXACT:
        return True
    if key_l.endswith("_sig"):
        return True
    return any(part in key_l for part in SENSITIVE_KEY_PARTS)


def redact(data):
    if isinstance(data, dict):
        return {
            key: MASK if is_sensitive_key(str(key)) else redact(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [redact(value) for value in data]
    return data


def redact_line(line: str) -> str:
    for separator in (":", "="):
        if separator in line:
            key, _value = line.split(separator, 1)
            if is_sensitive_key(key.strip()):
                return f"{key}{separator} {MASK}"
            return line
    return line


def redact_lines(lines: List[str]) -> List[str]:
    return [redact_line(line) for line in lines]


def redact_text_bytes(data: bytes) -> bytes:
    text = ANSI_RE.sub("", data.decode("utf-8", errors="replace"))
    lines = redact_lines(text.splitlines())
    text = "\n".join(lines)
    text = re.sub(r"(?i)(ssid|password|token|secret|api[_-]?key)=([^,\s]+)", r"\1=<redacted>", text)
    return (text + "\n").encode("utf-8")
