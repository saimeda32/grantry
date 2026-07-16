"""Logging whose handler redacts secrets by construction. No call site is trusted."""

from __future__ import annotations

import logging
import re

_KEYS = "accessKeyId|secretAccessKey|sessionToken|accessToken|clientSecret|refreshToken"
_KV = re.compile(rf'(?i)("?({_KEYS})"?\s*[=:]\s*"?)([^"\s,}}]+)')
# Any long token-like run (>=20 chars of base64/hex-ish material).
_BLOB = re.compile(r"[A-Za-z0-9/+_-]{20,}")


def redact(text: str) -> str:
    text = _KV.sub(lambda m: m.group(1) + "***", text)
    text = _BLOB.sub("***", text)
    return text


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.getMessage()))
        record.args = ()
        return True


def configure_logging(verbosity: int = 0) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    handler = logging.StreamHandler()
    handler.addFilter(_RedactFilter())
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
