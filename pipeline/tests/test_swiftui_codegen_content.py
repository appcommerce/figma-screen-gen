from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pipeline.src.generate_ui import main


@pytest.mark.skipif(shutil.which("swift") is None, reason="swift toolchain is required")
def test_swiftui_codegen_maps_core_dsl_nodes(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_ui",
            "--config",
            "pipeline/config/pipeline-config.yaml",
            "--figma-json",
            "pipeline/tests/fixtures/sample_figma_nodes.json",
            "--out-root",
            ".",
            "--target",
            "swiftui",
            "--swiftui-backend",
            "native_swift",
        ],
    )
    main()

    generated = Path("generated/swiftui/screens/ProductDetailsScreen.swift")
    assert generated.exists()
    source = generated.read_text(encoding="utf-8")

    # screen/page -> ScrollView
    assert "ScrollView {" in source
    # layout/column -> VStack
    assert "VStack(alignment: .leading" in source
    # content/text -> Text
    assert "Text(\"Product details\")" in source
    # component/checkbox -> Toggle
    assert "Toggle(isOn: .constant(true))" in source
    # content/icon -> Image(resourceName)
    assert "Image(\"cart\")" in source
    # screen/bottomSheet mapping
    assert ".background(.ultraThinMaterial)" in source
