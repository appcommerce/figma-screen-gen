from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from typing import Any


class QualityGates:
    def __init__(self, snapshots_dir: Path, reports_dir: Path) -> None:
        self.snapshots_dir = snapshots_dir
        self.reports_dir = reports_dir
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def snapshot_json(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        target = self.snapshots_dir / f"{name}.json"
        raw = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        changed = True
        diff = ""
        if target.exists():
            old = target.read_text(encoding="utf-8")
            changed = old != raw
            if changed:
                diff = "\n".join(
                    difflib.unified_diff(
                        old.splitlines(),
                        raw.splitlines(),
                        fromfile=f"old/{name}.json",
                        tofile=f"new/{name}.json",
                        lineterm="",
                    )
                )
        target.write_text(raw, encoding="utf-8")
        return {"name": name, "hash": digest, "changed": changed, "diff": diff}

    def validate_asset_refs(self, dsl: dict[str, Any], asset_manifest: dict[str, Any]) -> list[dict[str, Any]]:
        resources: set[str] = set()
        for asset in asset_manifest.get("assets", []):
            drawable = asset.get("drawableResourceName")
            ios_asset = asset.get("iosAssetName")
            if drawable:
                resources.add(str(drawable))
            if ios_asset:
                resources.add(str(ios_asset))
        issues: list[dict[str, Any]] = []
        for screen in dsl.get("screens", []):
            for node in _walk_nodes(screen):
                resource_name = node.get("props", {}).get("resourceName")
                asset_ref = node.get("props", {}).get("assetRef")
                if resource_name and resource_name not in resources:
                    issues.append(
                        {
                            "severity": "error",
                            "code": "UNRESOLVED_RESOURCE_NAME",
                            "nodeId": node.get("id"),
                            "message": f"resourceName '{resource_name}' is not found in asset manifest",
                        }
                    )
                if asset_ref and asset_ref not in resources:
                    issues.append(
                        {
                            "severity": "error",
                            "code": "UNRESOLVED_ASSET_REF",
                            "nodeId": node.get("id"),
                            "message": f"assetRef '{asset_ref}' is not found in asset manifest",
                        }
                    )
        return issues

    def write_pipeline_report(self, report: dict[str, Any]) -> Path:
        path = self.reports_dir / "pipeline-quality-report.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return path


def _walk_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    stack = [node]
    out: list[dict[str, Any]] = []
    while stack:
        current = stack.pop()
        out.append(current)
        stack.extend(current.get("children", []))
    return out
