from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

from .naming_contract import NamingContract, NamingIssue


SUPPORTED_ASSET_COMPONENTS = {"icon", "image", "illustration"}
VECTOR_LIKE_NODE_TYPES = {"VECTOR", "BOOLEAN_OPERATION", "STAR", "LINE", "ELLIPSE", "POLYGON"}


def _load_schema(schema_path: Path) -> dict[str, Any]:
    return json.loads(schema_path.read_text(encoding="utf-8"))


class FigmaToJsonConverter:
    def __init__(
        self,
        naming_contract_path: Path,
        schema_path: Path,
        reports_dir: Path,
    ) -> None:
        self.naming_contract = NamingContract(naming_contract_path)
        self.schema = _load_schema(schema_path)
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def convert(
        self,
        figma_payload: dict[str, Any],
        file_key: str,
        selected_node_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        issues: list[NamingIssue] = []
        assets: list[dict[str, Any]] = []
        screens: list[dict[str, Any]] = []

        for node in figma_payload.get("nodes", []):
            normalized_node, node_issues, node_assets = self._normalize_node(node)
            issues.extend(node_issues)
            assets.extend(node_assets)
            screens.append(normalized_node)
            issues.extend(self.naming_contract.validate_modal_hierarchy(normalized_node))

        result = {
            "version": "1.0.0",
            "source": {
                "fileKey": file_key,
                "generatedAt": datetime.now(tz=UTC).isoformat(),
                "nodeIds": selected_node_ids or [n.get("id", "") for n in figma_payload.get("nodes", [])],
            },
            "screens": screens,
            "assets": assets,
            "issues": [
                {
                    "severity": issue.severity,
                    "code": issue.code,
                    "message": issue.message,
                    "nodeId": issue.node_id,
                }
                for issue in issues
            ],
        }
        jsonschema.validate(instance=result, schema=self.schema)
        self._write_naming_report(result)
        return result

    def _normalize_node(self, node: dict[str, Any]) -> tuple[dict[str, Any], list[NamingIssue], list[dict[str, Any]]]:
        naming = self.naming_contract.parse(name=node.get("name", ""), node_id=node.get("id", ""))
        issues = list(naming.issues)
        assets: list[dict[str, Any]] = []

        normalized_children: list[dict[str, Any]] = []
        for child in node.get("children", []):
            child_normalized, child_issues, child_assets = self._normalize_node(child)
            normalized_children.append(child_normalized)
            issues.extend(child_issues)
            assets.extend(child_assets)

        normalized = {
            "id": str(node.get("id", "")),
            "type": str(node.get("type", "UNKNOWN")),
            "name": str(node.get("name", "")),
            "naming": {
                "rawName": naming.raw_name,
                "level": naming.level,
                "component": naming.component,
                "semanticName": naming.semantic_name,
                "variant": naming.variant,
                "state": naming.state,
                "role": naming.role,
                "valid": naming.valid,
            },
            "bounds": {
                "x": float(node.get("absoluteBoundingBox", {}).get("x", 0)),
                "y": float(node.get("absoluteBoundingBox", {}).get("y", 0)),
                "width": float(node.get("absoluteBoundingBox", {}).get("width", 0)),
                "height": float(node.get("absoluteBoundingBox", {}).get("height", 0)),
            },
            "layout": {
                "mode": node.get("layoutMode", "NONE"),
                "constraints": {
                    "horizontal": node.get("constraints", {}).get("horizontal", "LEFT"),
                    "vertical": node.get("constraints", {}).get("vertical", "TOP"),
                },
                "padding": {
                    "left": float(node.get("paddingLeft", 0)),
                    "right": float(node.get("paddingRight", 0)),
                    "top": float(node.get("paddingTop", 0)),
                    "bottom": float(node.get("paddingBottom", 0)),
                },
                "itemSpacing": float(node.get("itemSpacing", 0)),
            },
            "style": {
                "fill": _extract_primary_fill(node.get("fills", [])),
                "textStyleRef": str(node.get("style", {}).get("name", "")) or None,
                "fontSize": _safe_float(node.get("style", {}).get("fontSize")),
                "lineHeight": _safe_float(node.get("style", {}).get("lineHeightPx")),
                "cornerRadius": _safe_float(node.get("cornerRadius")),
                "opacity": _safe_float(node.get("opacity")),
            },
            "children": normalized_children,
        }
        normalized["naming"] = {k: v for k, v in normalized["naming"].items() if v is not None}
        normalized["style"] = {k: v for k, v in normalized["style"].items() if v is not None}
        if node.get("characters") is not None:
            normalized["text"] = node.get("characters")

        asset_kind = _infer_asset_kind(node=node, naming_component=naming.component)
        if asset_kind is not None:
            resource_name = _normalize_resource_name(f"{naming.semantic_name}_{node.get('id', '')}")
            content_hash = hashlib.sha256(
                json.dumps(
                    {
                        "id": node.get("id"),
                        "name": node.get("name"),
                        "bounds": normalized["bounds"],
                        "fills": node.get("fills"),
                    },
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()[:16]
            asset_metadata = {
                "figmaNodeId": str(node.get("id", "")),
                "assetKind": asset_kind,
                "exportFormat": "SVG",
                "resourceName": resource_name,
                "contentHash": content_hash,
                "svgPath": f"pipeline/assets/svg/{resource_name}.svg",
                "drawableXmlPath": f"app/src/main/res/drawable/{resource_name}.xml",
            }
            assets.append(asset_metadata)
            normalized["assetRef"] = resource_name
            if naming.component not in SUPPORTED_ASSET_COMPONENTS:
                issues.append(
                    NamingIssue(
                        severity="warning",
                        code="ASSET_INFERRED_FROM_NODE_TYPE",
                        message=f"Asset kind '{asset_kind}' inferred from Figma node type '{node.get('type')}'",
                        node_id=str(node.get("id", "")),
                    )
                )
        return normalized, issues, assets

    def _write_naming_report(self, ir: dict[str, Any]) -> None:
        total_nodes = 0
        invalid_nodes = 0
        for screen in ir["screens"]:
            for node in _walk_nodes(screen):
                total_nodes += 1
                if not node.get("naming", {}).get("valid", False):
                    invalid_nodes += 1
        warnings = [x for x in ir["issues"] if x["severity"] == "warning"]
        errors = [x for x in ir["issues"] if x["severity"] == "error"]
        report = {
            "totalNodes": total_nodes,
            "invalidNodes": invalid_nodes,
            "warningsCount": len(warnings),
            "errorsCount": len(errors),
            "warnings": warnings,
            "errors": errors,
        }
        (self.reports_dir / "naming-contract-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _walk_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    stack = [node]
    out: list[dict[str, Any]] = []
    while stack:
        current = stack.pop()
        out.append(current)
        stack.extend(current.get("children", []))
    return out


def _normalize_resource_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value.lower())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.strip("_")
    if not cleaned:
        return "asset_unknown"
    if cleaned[0].isdigit():
        return f"asset_{cleaned}"
    return cleaned


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_primary_fill(fills: Any) -> str | None:
    if not isinstance(fills, list) or not fills:
        return None
    first = fills[0]
    if not isinstance(first, dict):
        return None
    color = first.get("color")
    if not isinstance(color, dict):
        return None
    r = int(float(color.get("r", 0)) * 255)
    g = int(float(color.get("g", 0)) * 255)
    b = int(float(color.get("b", 0)) * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


def _infer_asset_kind(node: dict[str, Any], naming_component: str) -> str | None:
    if naming_component in SUPPORTED_ASSET_COMPONENTS:
        return naming_component
    node_type = str(node.get("type", "")).upper()
    if node_type in VECTOR_LIKE_NODE_TYPES:
        return "icon"
    if _has_image_fill(node.get("fills", [])):
        return "image"
    return None


def _has_image_fill(fills: Any) -> bool:
    if not isinstance(fills, list):
        return False
    for fill in fills:
        if isinstance(fill, dict) and str(fill.get("type", "")).upper() == "IMAGE":
            return True
    return False
