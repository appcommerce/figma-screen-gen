from __future__ import annotations

from pathlib import Path

from pipeline.src.generate_ui import main


def test_compose_codegen_maps_core_dsl_nodes(monkeypatch) -> None:
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
            "compose",
        ],
    )
    main()

    generated = Path("generated/compose/src/main/java/com/example/generated/screens/ProductDetailsScreen.kt")
    assert generated.exists()
    source = generated.read_text(encoding="utf-8")

    # screen/page -> LazyColumn
    assert "LazyColumn(" in source
    # layout/column -> Column
    assert "Column(" in source
    # content/text -> Text
    assert 'Text(' in source and 'text = "Product details"' in source
    # checkbox component
    assert "Checkbox(" in source
    # icon asset mapping
    assert "R.drawable.cart" in source
    # bottom sheet mapping
    assert "ModalBottomSheet(" in source
