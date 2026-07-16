"""Append-only audit of every grant decision. Never contains a secret."""

from __future__ import annotations

import json
import os
from typing import Any

from grantry.config import state_path
from grantry.identity import Identity
from grantry.policy import Decision


class AuditLog:
    def __init__(self) -> None:
        self._path = state_path("audit.jsonl")
        if not self._path.exists():
            fd = os.open(self._path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)

    def record(self, caller: str, ident: Identity, decision: Decision, at: str) -> None:
        entry: dict[str, Any] = {
            "at": at,
            "caller": caller,
            "identity": ident.key,
            "account_id": ident.account_id,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "matched_rule": decision.matched_rule,
            "capped_ttl": decision.capped_ttl,
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":")) + "\n")

    def entries(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out
