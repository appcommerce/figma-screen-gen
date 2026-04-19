from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class NamingIssue:
    severity: str
    code: str
    message: str
    node_id: str


@dataclass(slots=True)
class ParsedName:
    raw_name: str
    level: str
    component: str
    semantic_name: str
    variant: str | None
    state: str | None
    role: str | None
    valid: bool
    issues: list[NamingIssue]


class NamingContract:
    def __init__(self, config_path: Path) -> None:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self._regex = re.compile(payload["naming"]["regex"])
        self._allowed_levels = set(payload["naming"]["allowed_levels"])
        self._allowed_variants = set(payload["naming"]["allowed_variants"])
        self._allowed_states = set(payload["naming"]["allowed_states"])
        self._allowed_roles = set(payload["naming"]["allowed_roles"])
        self._component_to_level = dict(payload["component_to_level"])
        self._screen_modal_rules = payload.get("screen_modal_rules", {})

    def parse(self, name: str, node_id: str) -> ParsedName:
        issues: list[NamingIssue] = []
        match = self._regex.match(name)
        if not match:
            issues.append(
                NamingIssue(
                    severity="warning",
                    code="NAMING_REGEX_MISMATCH",
                    message=f"Node name '{name}' does not match naming contract",
                    node_id=node_id,
                )
            )
            return ParsedName(
                raw_name=name,
                level="raw",
                component="frame",
                semantic_name=self._fallback_semantic_name(name),
                variant=None,
                state=None,
                role=None,
                valid=False,
                issues=issues,
            )

        level = match.group("level")
        component = match.group("component")
        semantic_name = match.group("semanticName")
        variant = match.group("variant")
        state = match.group("state")
        role = match.group("role")

        if level not in self._allowed_levels:
            issues.append(
                NamingIssue(
                    severity="error",
                    code="UNKNOWN_LEVEL",
                    message=f"Unknown level '{level}'",
                    node_id=node_id,
                )
            )
        expected_level = self._component_to_level.get(component)
        if expected_level is None:
            issues.append(
                NamingIssue(
                    severity="error",
                    code="UNKNOWN_COMPONENT",
                    message=f"Unknown component '{component}'",
                    node_id=node_id,
                )
            )
        elif expected_level != level:
            issues.append(
                NamingIssue(
                    severity="error",
                    code="LEVEL_COMPONENT_MISMATCH",
                    message=f"Component '{component}' must use level '{expected_level}', got '{level}'",
                    node_id=node_id,
                )
            )
        if variant is not None and variant not in self._allowed_variants:
            issues.append(
                NamingIssue(
                    severity="warning",
                    code="UNKNOWN_VARIANT",
                    message=f"Unknown variant '{variant}'",
                    node_id=node_id,
                )
            )
        if state is not None and state not in self._allowed_states:
            issues.append(
                NamingIssue(
                    severity="warning",
                    code="UNKNOWN_STATE",
                    message=f"Unknown state '{state}'",
                    node_id=node_id,
                )
            )
        if role is not None and role not in self._allowed_roles:
            issues.append(
                NamingIssue(
                    severity="warning",
                    code="UNKNOWN_ROLE",
                    message=f"Unknown role '{role}'",
                    node_id=node_id,
                )
            )
        has_error = any(issue.severity == "error" for issue in issues)
        return ParsedName(
            raw_name=name,
            level=level,
            component=component,
            semantic_name=semantic_name,
            variant=variant,
            state=state,
            role=role,
            valid=not has_error,
            issues=issues,
        )

    def validate_modal_hierarchy(self, root_node: dict[str, Any]) -> list[NamingIssue]:
        issues: list[NamingIssue] = []
        if not self._screen_modal_rules.get("require_nested_modal_screens", False):
            return issues

        def walk(node: dict[str, Any], ancestors: list[dict[str, Any]]) -> None:
            naming = node.get("naming", {})
            component = naming.get("component")
            level = naming.get("level")
            if level == "screen" and component in {"bottomSheet", "dialog"}:
                has_screen_ancestor = any(
                    anc.get("naming", {}).get("level") == "screen" and anc.get("naming", {}).get("component") == "page"
                    for anc in ancestors
                )
                if not has_screen_ancestor:
                    issues.append(
                        NamingIssue(
                            severity="error",
                            code="MODAL_SCREEN_NOT_NESTED",
                            message=f"Modal screen '{component}' must be nested under screen/page",
                            node_id=node.get("id", ""),
                        )
                    )
            for child in node.get("children", []):
                walk(child, ancestors + [node])

        walk(root_node, [])
        return issues

    @staticmethod
    def _fallback_semantic_name(name: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9]+", " ", name).strip()
        if not sanitized:
            return "unknownNode"
        parts = sanitized.split()
        head = parts[0].lower()
        tail = "".join(p[:1].upper() + p[1:] for p in parts[1:])
        return f"{head}{tail}"[:80]
