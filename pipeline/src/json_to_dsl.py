from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml


def _load_yaml_schema(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class JsonToDslConverter:
    def __init__(self, dsl_schema_path: Path) -> None:
        self.dsl_schema = _load_yaml_schema(dsl_schema_path)

    def convert(self, ir: dict[str, Any]) -> dict[str, Any]:
        dsl = {
            "version": "1.0.0",
            "screens": [self._node_to_dsl(screen) for screen in ir["screens"]],
            "assets": [
                {
                    "resourceName": asset["resourceName"],
                    "assetKind": asset["assetKind"],
                    "figmaNodeId": asset["figmaNodeId"],
                }
                for asset in ir.get("assets", [])
            ],
            "metadata": {
                "sourceFileKey": ir["source"]["fileKey"],
                "generatedAt": ir["source"]["generatedAt"],
            },
        }
        jsonschema.validate(instance=dsl, schema=self.dsl_schema)
        return dsl

    def dump_yaml(self, dsl: dict[str, Any], path: Path) -> None:
        path.write_text(
            yaml.safe_dump(dsl, allow_unicode=False, sort_keys=False),
            encoding="utf-8",
        )

    def _node_to_dsl(self, node: dict[str, Any]) -> dict[str, Any]:
        naming = node["naming"]
        props: dict[str, Any] = {
            "widthDp": node["bounds"]["width"],
            "heightDp": node["bounds"]["height"],
            "xDp": node["bounds"]["x"],
            "yDp": node["bounds"]["y"],
            "padding": {
                "leftDp": node["layout"]["padding"]["left"],
                "rightDp": node["layout"]["padding"]["right"],
                "topDp": node["layout"]["padding"]["top"],
                "bottomDp": node["layout"]["padding"]["bottom"],
            },
            "spacingDp": node["layout"]["itemSpacing"],
            "layout": _layout_mode_to_dsl(node["layout"].get("mode")),
            "styleRef": node["style"].get("textStyleRef"),
            "tokenRef": node["style"].get("fill"),
            "text": node.get("text"),
            "testTag": f"{naming['component']}_{naming['semanticName']}",
            "contentDescription": naming["semanticName"],
        }
        if node.get("assetRef"):
            props["assetRef"] = node["assetRef"]
            props["resourceName"] = node["assetRef"]
            props["assetKind"] = naming["component"]

        dsl_node = {
            "id": node["id"],
            "node": f"{naming['level']}/{naming['component']}",
            "name": naming["semanticName"],
            "variant": naming.get("variant"),
            "state": naming.get("state"),
            "role": naming.get("role"),
            "props": props,
            "children": [self._node_to_dsl(x) for x in node.get("children", [])],
        }
        return _strip_none(dsl_node)


def _strip_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_none(v) for v in value]
    return value


def _layout_mode_to_dsl(layout_mode: str | None) -> str:
    if layout_mode == "HORIZONTAL":
        return "row"
    if layout_mode == "VERTICAL":
        return "column"
    if layout_mode == "GRID":
        return "grid"
    return "box"


def dump_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
