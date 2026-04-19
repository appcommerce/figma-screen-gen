from __future__ import annotations

import json
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

    report_path = Path("generated/reports/pipeline-quality-report.json")
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    compose_codegen = report["composeCodegen"]
    assert compose_codegen["delegated"] is True
    assert compose_codegen["dslPath"].endswith("generated/dsl/ui_dsl.yaml")
    assert compose_codegen["outputRoot"].endswith("generated/compose/src/main/java")
    assert compose_codegen["packageName"] == "com.example.generated"
