"""OS-keychain secret storage. Secrets never touch the state directory or a log."""

from __future__ import annotations

import hashlib

import keyring

_SERVICE = "grantry"


class SecretStore:
    def put(self, name: str, value: str) -> None:
        keyring.set_password(_SERVICE, name, value)

    def get(self, name: str) -> str | None:
        return keyring.get_password(_SERVICE, name)

    def delete(self, name: str) -> None:
        keyring.delete_password(_SERVICE, name)


def token_name(start_url: str) -> str:
    digest = hashlib.sha256(start_url.encode("utf-8")).hexdigest()[:16]
    return f"sso-token:{digest}"
