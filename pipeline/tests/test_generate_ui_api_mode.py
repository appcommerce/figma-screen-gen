from __future__ import annotations

import json
from pathlib import Path

from pipeline.src import generate_ui


class _FakeFigmaApiClient:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def fetch_nodes(self, file_key: str, node_ids: list[str]) -> dict:
        assert file_key == "api_demo"
        assert node_ids == ["1:1"]
        return {
            "nodes": [
                {
                    "id": "1:1",
                    "type": "FRAME",
                    "name": "screen/page/productDetails",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 360, "height": 800},
                    "layoutMode": "VERTICAL",
                    "children": [
                        {
                            "id": "1:2",
                            "type": "VECTOR",
                            "name": "content/icon/cart",
                            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 24, "height": 24},
                        }
                    ],
                }
            ]
        }

    def fetch_svg_assets(self, file_key: str, figma_node_ids: list[str]) -> dict[str, str]:
        assert file_key == "api_demo"
        assert figma_node_ids == ["1:2"]
        return {
            "1:2": "<svg width=\"24\" height=\"24\" viewBox=\"0 0 24 24\"><path d=\"M0 0 L24 24\" fill=\"#FF0000\"/></svg>"
        }


def test_pipeline_works_in_figma_api_mode(monkeypatch) -> None:
    monkeypatch.setattr(generate_ui, "FigmaApiClient", _FakeFigmaApiClient)
    monkeypatch.setenv("FIGMA_TOKEN", "token_for_test")
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_ui",
            "--file-key",
            "api_demo",
            "--node",
            "1:1",
            "--out-root",
            ".",
        ],
    )

    generate_ui.main()

    assert Path("generated/reports/asset-manifest.json").exists()
    manifest = json.loads(Path("generated/reports/asset-manifest.json").read_text(encoding="utf-8"))
    assert manifest["assets"] == []
