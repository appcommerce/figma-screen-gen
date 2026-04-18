from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

from pipeline.src import generate_ui


def test_pipeline_generates_swiftui_with_native_backend(monkeypatch) -> None:
    def _fake_swift_run(command: list[str], check: bool, text: bool, capture_output: bool) -> CompletedProcess[str]:
        assert check is False
        assert text is True
        assert capture_output is True
        assert command[:2] == ["swift", "run"]
        output_dir = Path(command[command.index("--output-dir") + 1])
        (output_dir / "screens").mkdir(parents=True, exist_ok=True)
        (output_dir / "previews").mkdir(parents=True, exist_ok=True)
        (output_dir / "screens" / "PageProductDetailsScreen.swift").write_text("import SwiftUI\n", encoding="utf-8")
        (output_dir / "previews" / "PageProductDetailsPreview.swift").write_text("import SwiftUI\n", encoding="utf-8")
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(generate_ui.subprocess, "run", _fake_swift_run)
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
            "--target",
            "swiftui",
            "--swiftui-backend",
            "native_swift",
        ],
    )

    generate_ui.main()

    assert Path("generated/swiftui/screens/PageProductDetailsScreen.swift").exists()
    assert Path("generated/swiftui/previews/PageProductDetailsPreview.swift").exists()
