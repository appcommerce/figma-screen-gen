from pathlib import Path

from pipeline.src.generate_ui import main


def test_pipeline_generates_artifacts(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_ui",
            "--figma-json",
            "pipeline/tests/fixtures/sample_figma_nodes.json",
            "--file-key",
            "demo_file",
            "--out-root",
            ".",
        ],
    )
    main()

    assert Path("generated/ir/ui_ir.json").exists()
    assert Path("generated/dsl/ui_dsl.yaml").exists()
    assert Path("generated/reports/naming-contract-report.json").exists()
    assert Path("generated/reports/asset-manifest.json").exists()
    assert Path("generated/reports/pipeline-quality-report.json").exists()


def test_pipeline_uses_config_file(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_ui",
            "--config",
            "pipeline/tests/fixtures/pipeline-config.fixture.yaml",
            "--out-root",
            ".",
        ],
    )
    main()
    assert Path("generated/ir/ui_ir.json").exists()
