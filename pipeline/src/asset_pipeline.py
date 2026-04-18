from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AssetIssue:
    severity: str
    code: str
    message: str
    figma_node_id: str
    resource_name: str


class AssetPipeline:
    def __init__(
        self,
        svg_dir: Path,
        drawable_dir: Path,
        ios_assets_dir: Path | None,
        reports_dir: Path,
    ) -> None:
        self.svg_dir = svg_dir
        self.drawable_dir = drawable_dir
        self.ios_assets_dir = ios_assets_dir
        self.reports_dir = reports_dir
        self.logger = logging.getLogger("pipeline.assets")
        self.svg_dir.mkdir(parents=True, exist_ok=True)
        self.drawable_dir.mkdir(parents=True, exist_ok=True)
        if self.ios_assets_dir is not None:
            self.ios_assets_dir.mkdir(parents=True, exist_ok=True)
            self._write_ios_root_contents()
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def process_assets(
        self,
        assets: list[dict[str, Any]],
        svg_by_figma_node_id: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        manifest_items: list[dict[str, Any]] = []
        issues: list[AssetIssue] = []
        svg_by_figma_node_id = svg_by_figma_node_id or {}
        self.logger.info("Asset pipeline started: assets=%s", len(assets))

        for idx, asset in enumerate(assets, start=1):
            figma_node_id = asset["figmaNodeId"]
            resource_name = asset["resourceName"]
            svg_path = self.svg_dir / f"{resource_name}.svg"
            drawable_path = self.drawable_dir / f"{resource_name}.xml"

            downloaded_svg = svg_by_figma_node_id.get(figma_node_id)
            if downloaded_svg:
                svg_path.write_text(downloaded_svg, encoding="utf-8")
            elif not svg_path.exists():
                svg_path.write_text(_default_svg(resource_name), encoding="utf-8")
                issues.append(
                    AssetIssue(
                        severity="warning",
                        code="ASSET_FALLBACK_PLACEHOLDER",
                        message="SVG was not downloaded from Figma API, placeholder was generated",
                        figma_node_id=figma_node_id,
                        resource_name=resource_name,
                    )
                )

            svg_text = svg_path.read_text(encoding="utf-8")
            xml, ok = _svg_to_vector_drawable(svg_text, resource_name)
            if not ok:
                issues.append(
                    AssetIssue(
                        severity="warning",
                        code="SVG_TO_VECTOR_PARTIAL",
                        message="SVG conversion is partial; fallback VectorDrawable generated",
                        figma_node_id=figma_node_id,
                        resource_name=resource_name,
                    )
                )
            drawable_path.write_text(xml, encoding="utf-8")
            ios_imageset_path: str | None = None
            if self.ios_assets_dir is not None:
                ios_imageset = self._write_ios_imageset(resource_name=resource_name, svg_text=svg_text)
                ios_imageset_path = str(ios_imageset)

            manifest_items.append(
                {
                    "figmaNodeId": figma_node_id,
                    "svgPath": str(svg_path),
                    "drawableResourceName": resource_name,
                    "drawableXmlPath": str(drawable_path),
                    "iosAssetName": resource_name,
                    "iosImagesetPath": ios_imageset_path,
                }
            )
            if idx <= 10 or idx % 25 == 0:
                self.logger.info("Asset processed %s/%s: %s", idx, len(assets), resource_name)

        manifest = {
            "assets": manifest_items,
            "issues": [asdict(issue) for issue in issues],
        }
        (self.reports_dir / "asset-manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.logger.info(
            "Asset pipeline finished: manifest_assets=%s issues=%s",
            len(manifest_items),
            len(issues),
        )
        return manifest

    def _write_ios_root_contents(self) -> None:
        if self.ios_assets_dir is None:
            return
        contents = {
            "info": {
                "author": "xcode",
                "version": 1,
            }
        }
        (self.ios_assets_dir / "Contents.json").write_text(
            json.dumps(contents, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_ios_imageset(self, resource_name: str, svg_text: str) -> Path:
        if self.ios_assets_dir is None:
            raise ValueError("ios_assets_dir is not configured")
        imageset_dir = self.ios_assets_dir / f"{resource_name}.imageset"
        imageset_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{resource_name}.svg"
        (imageset_dir / filename).write_text(svg_text, encoding="utf-8")
        contents = {
            "images": [
                {
                    "filename": filename,
                    "idiom": "universal",
                }
            ],
            "info": {
                "author": "xcode",
                "version": 1,
            },
        }
        (imageset_dir / "Contents.json").write_text(
            json.dumps(contents, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return imageset_dir


def _svg_to_vector_drawable(svg_text: str, resource_name: str) -> tuple[str, bool]:
    width = _extract_dimension(svg_text, "width") or 24
    height = _extract_dimension(svg_text, "height") or 24
    view_box = _extract_view_box(svg_text)
    if view_box is None:
        view_box = (0.0, 0.0, float(width), float(height))
    min_x, min_y, vb_width, vb_height = view_box

    path_match = re.search(r"d=\"([^\"]+)\"", svg_text)
    fill_match = re.search(r"fill=\"([#A-Fa-f0-9]{7})\"", svg_text)
    path_data = path_match.group(1) if path_match else "M0,0 L24,0 L24,24 L0,24 Z"
    fill = fill_match.group(1) if fill_match else "#FF000000"
    ok = path_match is not None

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:name="{resource_name}"
    android:width="{width}dp"
    android:height="{height}dp"
    android:viewportWidth="{vb_width}"
    android:viewportHeight="{vb_height}">
    <path
        android:fillColor="{fill}"
        android:pathData="{path_data}" />
</vector>
"""
    # min_x/min_y not used for now; TODO codegen can apply translation if needed.
    _ = (min_x, min_y)
    return xml, ok


def _extract_dimension(svg_text: str, attr: str) -> float | None:
    m = re.search(rf"{attr}=\"([0-9]+(?:\\.[0-9]+)?)\"", svg_text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _extract_view_box(svg_text: str) -> tuple[float, float, float, float] | None:
    m = re.search(r"viewBox=\"([^\"]+)\"", svg_text)
    if not m:
        return None
    chunks = m.group(1).strip().split()
    if len(chunks) != 4:
        return None
    try:
        return tuple(float(x) for x in chunks)  # type: ignore[return-value]
    except ValueError:
        return None


def _default_svg(resource_name: str) -> str:
    return f"""<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <path d="M2 2 L22 2 L22 22 L2 22 Z" fill="#FF000000"/>
</svg>
<!-- placeholder generated for {resource_name} -->
"""
