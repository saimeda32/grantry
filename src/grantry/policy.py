"""The policy layer between callers and the cloud. Fail closed for agents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from grantry.identity import Identity, matches
from grantry.ttl import parse_ttl

_DEFAULT_AGENT_TTL = 900  # 15m
_DEFAULT_HUMAN_TTL = 43200  # 12h


class PolicyError(Exception):
    pass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    matched_rule: str | None
    capped_ttl: int


@dataclass(frozen=True)
class _Section:
    allow: list[str]
    deny: list[str]
    max_ttl: int
    default_allow: bool


class Policy:
    def __init__(self, agents: _Section, humans: _Section, exists: bool) -> None:
        self._agents = agents
        self._humans = humans
        self._exists = exists

    @classmethod
    def load(cls, path: Path) -> Policy:
        if not path.exists():
            return cls(
                agents=_Section([], [], _DEFAULT_AGENT_TTL, default_allow=False),
                humans=_Section([], [], _DEFAULT_HUMAN_TTL, default_allow=True),
                exists=False,
            )
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as e:
            raise PolicyError(f"policy.yaml is not valid YAML: {e}") from e
        if not isinstance(raw, dict):
            raise PolicyError("policy.yaml must be a mapping with agents/humans sections")
        return cls(
            agents=cls._section(raw.get("agents"), _DEFAULT_AGENT_TTL, default_allow=False),
            humans=cls._section(raw.get("humans"), _DEFAULT_HUMAN_TTL, default_allow=True),
            exists=True,
        )

    @staticmethod
    def _section(node: Any, default_ttl: int, *, default_allow: bool) -> _Section:
        if node is None:
            return _Section([], [], default_ttl, default_allow)
        if not isinstance(node, dict):
            raise PolicyError("each policy section must be a mapping")
        allow = Policy._patterns(node.get("allow"))
        deny = Policy._patterns(node.get("deny"))
        max_ttl = default_ttl
        if "max_ttl" in node:
            try:
                max_ttl = parse_ttl(str(node["max_ttl"]))
            except ValueError as e:
                raise PolicyError(str(e)) from e
        return _Section(allow, deny, max_ttl, default_allow)

    @staticmethod
    def _patterns(node: Any) -> list[str]:
        if node is None:
            return []
        if not isinstance(node, list):
            raise PolicyError("allow/deny must be a list of {identity: pattern} entries")
        out: list[str] = []
        for entry in node:
            if not isinstance(entry, dict) or "identity" not in entry:
                raise PolicyError("each allow/deny entry needs an 'identity' pattern")
            out.append(str(entry["identity"]))
        return out

    def evaluate(self, ident: Identity, requested_ttl: int, caller: str = "agent") -> Decision:
        section = self._humans if caller == "human" else self._agents
        for pattern in section.deny:
            if matches(pattern, ident):
                return Decision(False, f"denied by deny rule {pattern!r}", pattern, 0)
        capped = min(requested_ttl, section.max_ttl)
        for pattern in section.allow:
            if matches(pattern, ident):
                return Decision(True, f"allowed by rule {pattern!r}", pattern, capped)
        if section.default_allow:
            return Decision(True, "allowed by default (human)", None, capped)
        return Decision(False, "no allow rule matched (agent default deny)", None, 0)
