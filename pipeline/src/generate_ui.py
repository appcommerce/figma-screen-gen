from __future__ import annotations

import argparse
import logging
import os
import json
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml

from .asset_pipeline import AssetPipeline
from .compose_generator import ComposeGenerator
from .figma_api import FigmaApiClient, FigmaApiConfig
from .figma_to_json import FigmaToJsonConverter
from .json_to_dsl import JsonToDslConverter, dump_json
from .quality_gates import QualityGates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate UI pipeline artifacts")
    parser.add_argument("--figma-json", help="Path to raw Figma nodes json payload")
    parser.add_argument("--file-key", help="Figma file key")
    parser.add_argument("--node", action="append", default=[], help="Optional selected Figma node id")
    parser.add_argument("--out-root", default=".", help="Project root")
    parser.add_argument("--package-name", help="Generated Compose package name")
    parser.add_argument("--figma-token", help="Figma API token (or use --figma-token-env)")
    parser.add_argument("--figma-token-env", help="Env var with Figma API token")
    parser.add_argument("--figma-base-url", help="Figma API base URL")
    parser.add_argument("--config", default="pipeline/config/pipeline-config.yaml", help="Pipeline config path")
    parser.add_argument("--log-level", default="INFO", help="Log level: DEBUG, INFO, WARNING, ERROR")
    parser.add_argument("--validate-only", action="store_true", help="Run until DSL validation and exit before Compose codegen")
    parser.add_argument(
        "--target",
        choices=("compose", "swiftui"),
        help="Generation target; overrides pipeline.target in config",
    )
    parser.add_argument(
        "--swiftui-backend",
        choices=("native_swift",),
        help="SwiftUI backend implementation; overrides pipeline.swiftui_codegen_backend",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _configure_logging(args.log_level)
    logger = logging.getLogger("pipeline")
    root = Path(args.out_root).resolve()
    _load_dotenv(root)
    logger.info("Pipeline started. root=%s config=%s", root, args.config)

    with _stage(logger, "load_config"):
        config = _load_pipeline_config(root=root, config_path=args.config)
        settings = _resolve_settings(args=args, config=config, root=root)
    with _stage(logger, "clean_outputs"):
        _cleanup_outputs(root=root, settings=settings, logger=logger)

    with _stage(logger, "load_figma_input"):
        payload, figma_client = _load_figma_input(settings)
        logger.info(
            "Figma payload loaded: screens=%s mode=%s",
            len(payload.get("nodes", [])),
            "json" if settings["figma"]["figma_json"] else "api",
        )

    naming_config = _resolve_path(root, settings["paths"]["naming_config"])
    ir_schema = _resolve_path(root, settings["paths"]["ir_schema"])
    dsl_schema = _resolve_path(root, settings["paths"]["dsl_schema"])
    reports_dir = _resolve_path(root, settings["paths"]["reports_dir"])
    generated_ir_dir = _resolve_path(root, settings["paths"]["generated_ir_dir"])
    generated_dsl_dir = _resolve_path(root, settings["paths"]["generated_dsl_dir"])
    drawable_dir = _resolve_path(root, settings["paths"]["drawable_dir"])
    svg_dir = _resolve_path(root, settings["paths"]["svg_dir"])
    ios_assets_dir = _resolve_path(root, settings["paths"]["ios_assets_dir"])
    generated_compose_dir = _resolve_path(root, settings["paths"]["generated_compose_dir"])
    generated_swiftui_dir = _resolve_path(root, settings["paths"]["generated_swiftui_dir"])
    swiftui_codegen_package_dir = _resolve_path(root, settings["paths"]["swiftui_codegen_package_dir"])
    snapshots_dir = _resolve_path(root, settings["paths"]["snapshots_dir"])

    generated_ir_dir.mkdir(parents=True, exist_ok=True)
    generated_dsl_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    with _stage(logger, "figma_to_ir"):
        figma_to_json = FigmaToJsonConverter(
            naming_contract_path=naming_config,
            schema_path=ir_schema,
            reports_dir=reports_dir,
        )
        ir = figma_to_json.convert(
            figma_payload=payload,
            file_key=settings["figma"]["file_key"],
            selected_node_ids=settings["figma"]["node_ids"] or None,
        )
        ir_path = generated_ir_dir / "ui_ir.json"
        dump_json(ir, ir_path)
        logger.info(
            "IR ready: screens=%s assets=%s issues=%s",
            len(ir.get("screens", [])),
            len(ir.get("assets", [])),
            len(ir.get("issues", [])),
        )

    assets_enabled = settings["pipeline"]["enable_assets"]
    if not assets_enabled:
        with _stage(logger, "disable_assets_mode"):
            for screen in ir.get("screens", []):
                _remove_asset_refs(screen)
            ir["assets"] = []
            dump_json(ir, ir_path)
            logger.info("Assets are disabled by config. IR asset metadata cleared.")

    svg_by_figma_node_id: dict[str, str] = {}
    if assets_enabled and figma_client is not None:
        with _stage(logger, "download_svg_assets"):
            asset_node_ids = [x["figmaNodeId"] for x in ir.get("assets", [])]
            logger.info("Asset candidates to download: %s", len(asset_node_ids))
            svg_by_figma_node_id = figma_client.fetch_svg_assets(
                file_key=settings["figma"]["file_key"],
                figma_node_ids=asset_node_ids,
            )
            logger.info("Downloaded SVG assets: %s", len(svg_by_figma_node_id))

    if assets_enabled:
        with _stage(logger, "asset_pipeline"):
            assets = AssetPipeline(
                svg_dir=svg_dir,
                drawable_dir=drawable_dir,
                ios_assets_dir=ios_assets_dir,
                reports_dir=reports_dir,
            )
            asset_manifest = assets.process_assets(
                ir.get("assets", []),
                svg_by_figma_node_id=svg_by_figma_node_id,
            )
            logger.info(
                "Assets processed: manifest=%s issues=%s",
                len(asset_manifest.get("assets", [])),
                len(asset_manifest.get("issues", [])),
            )
    else:
        with _stage(logger, "asset_pipeline_skipped"):
            asset_manifest = {"assets": [], "issues": []}
            _write_asset_manifest_placeholder(reports_dir, asset_manifest)
            logger.info("Asset stage skipped (enable_assets=false).")

    with _stage(logger, "ir_to_dsl"):
        dsl_converter = JsonToDslConverter(dsl_schema_path=dsl_schema)
        dsl = dsl_converter.convert(ir)
        dsl_path = generated_dsl_dir / "ui_dsl.yaml"
        dsl_converter.dump_yaml(dsl, dsl_path)
        logger.info("DSL ready: screens=%s assets=%s", len(dsl.get("screens", [])), len(dsl.get("assets", [])))

    with _stage(logger, "dsl_validation"):
        validation = _validate_dsl_mapping(
            dsl=dsl,
            ir=ir,
            naming_config_path=naming_config,
            reports_dir=reports_dir,
            fail_on_naming_error=settings["pipeline"]["fail_on_naming_error"],
            fail_on_naming_warning=settings["pipeline"]["fail_on_naming_warning"],
        )
        logger.info(
            "DSL validation: blocking=%s errors=%s warnings=%s dslIssues=%s",
            validation["blocking"],
            validation["namingErrors"],
            validation["namingWarnings"],
            validation["dslIssues"],
        )

    if args.validate_only:
        logger.info("Validate-only mode enabled. Codegen is skipped for target=%s.", settings["pipeline"]["target"])
        logger.info("Pipeline completed (validation only)")
        logger.info("IR: %s", ir_path)
        logger.info("DSL: %s", dsl_path)
        return

    generated_compose_files: list[Path] = []
    generated_swiftui_files: list[Path] = []
    target = settings["pipeline"]["target"]
    if target == "compose":
        with _stage(logger, "dsl_to_compose"):
            compose_generator = ComposeGenerator(
                output_root=generated_compose_dir,
                package_name=settings["pipeline"]["package_name"],
            )
            generated_compose_files = compose_generator.generate(dsl)
            logger.info("Compose generated files: %s", len(generated_compose_files))
    elif target == "swiftui":
        with _stage(logger, "dsl_to_swiftui"):
            backend = settings["pipeline"]["swiftui_codegen_backend"]
            if backend != "native_swift":
                raise ValueError(f"Unsupported swiftui backend '{backend}'")
            generated_swiftui_files = _run_native_swiftui_codegen(
                dsl=dsl,
                dsl_dir=generated_dsl_dir,
                output_dir=generated_swiftui_dir,
                swiftui_codegen_package_dir=swiftui_codegen_package_dir,
                swiftui_codegen_executable=settings["pipeline"]["swiftui_codegen_executable"],
                swiftui_module_name=settings["pipeline"]["swiftui_module_name"],
                logger=logger,
            )
            logger.info("SwiftUI generated files: %s", len(generated_swiftui_files))
    else:
        raise ValueError(f"Unsupported target '{target}'")

    with _stage(logger, "quality_gates"):
        quality = QualityGates(snapshots_dir=snapshots_dir, reports_dir=reports_dir)
        ir_snapshot = quality.snapshot_json("ui_ir", ir)
        dsl_snapshot = quality.snapshot_json("ui_dsl", dsl)
        unresolved_asset_refs = quality.validate_asset_refs(dsl, asset_manifest)
        quality_report = {
            "irSnapshot": ir_snapshot,
            "dslSnapshot": dsl_snapshot,
            "target": target,
            "generatedComposeFiles": [str(x) for x in generated_compose_files],
            "generatedSwiftUiFiles": [str(x) for x in generated_swiftui_files],
            "assetRefValidationIssues": unresolved_asset_refs,
        }
        quality.write_pipeline_report(quality_report)
        logger.info("Quality report issues: %s", len(unresolved_asset_refs))

    logger.info("Pipeline completed")
    logger.info("IR: %s", ir_path)
    logger.info("DSL: %s", dsl_path)
    logger.info("Target: %s", target)
    logger.info("Generated compose files: %s", len(generated_compose_files))
    logger.info("Generated swiftui files: %s", len(generated_swiftui_files))


def _load_pipeline_config(root: Path, config_path: str) -> dict[str, Any]:
    path = _resolve_path(root, config_path)
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_dotenv(root: Path) -> None:
    dotenv_path = root / ".env"
    if not dotenv_path.exists():
        return
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            continue
        cleaned = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, cleaned)


def _resolve_settings(args: argparse.Namespace, config: dict[str, Any], root: Path) -> dict[str, Any]:
    figma_cfg = config.get("figma", {})
    pipeline_cfg = config.get("pipeline", {})
    paths_cfg = config.get("paths", {})

    package_name = args.package_name or pipeline_cfg.get("package_name") or "com.example.generated"
    generated_compose_default = f"generated/compose/src/main/java/{package_name.replace('.', '/')}"
    resolved = {
        "figma": {
            "file_key": args.file_key or figma_cfg.get("file_key"),
            "node_ids": args.node or figma_cfg.get("node_ids") or [],
            "figma_json": args.figma_json or figma_cfg.get("figma_json"),
            "token": args.figma_token or figma_cfg.get("token"),
            "token_env": args.figma_token_env or figma_cfg.get("token_env") or "FIGMA_TOKEN",
            "base_url": args.figma_base_url or figma_cfg.get("base_url") or "https://api.figma.com/v1",
        },
        "pipeline": {
            "package_name": package_name,
            "target": args.target or pipeline_cfg.get("target") or "compose",
            "enable_assets": bool(pipeline_cfg.get("enable_assets", True)),
            "fail_on_naming_error": bool(pipeline_cfg.get("fail_on_naming_error", True)),
            "fail_on_naming_warning": bool(pipeline_cfg.get("fail_on_naming_warning", True)),
            "clean_before_generate": bool(pipeline_cfg.get("clean_before_generate", True)),
            "swiftui_codegen_backend": args.swiftui_backend or pipeline_cfg.get("swiftui_codegen_backend") or "native_swift",
            "swiftui_codegen_executable": pipeline_cfg.get("swiftui_codegen_executable") or "SwiftUICodegen",
            "swiftui_module_name": pipeline_cfg.get("swiftui_module_name") or "GeneratedSwiftUI",
            "legacy_cleanup_paths": pipeline_cfg.get(
                "legacy_cleanup_paths",
                [
                    "pipeline/generated_ir",
                    "pipeline/generated_dsl",
                    "pipeline/reports",
                    "pipeline/assets",
                    "pipeline/snapshots",
                    "app/src/main/java/com/example/generated",
                ],
            ),
        },
        "paths": {
            "naming_config": paths_cfg.get("naming_config", "pipeline/config/node-mapping.yaml"),
            "ir_schema": paths_cfg.get("ir_schema", "pipeline/schemas/ui_ir.schema.json"),
            "dsl_schema": paths_cfg.get("dsl_schema", "pipeline/schemas/ui_dsl.schema.yaml"),
            "reports_dir": paths_cfg.get("reports_dir", "generated/reports"),
            "generated_ir_dir": paths_cfg.get("generated_ir_dir", "generated/ir"),
            "generated_dsl_dir": paths_cfg.get("generated_dsl_dir", "generated/dsl"),
            "drawable_dir": paths_cfg.get("drawable_dir", "generated/resources/drawable"),
            "svg_dir": paths_cfg.get("svg_dir", "generated/assets/svg"),
            "ios_assets_dir": paths_cfg.get("ios_assets_dir", "generated/resources/ios/Assets.xcassets"),
            "snapshots_dir": paths_cfg.get("snapshots_dir", "generated/snapshots"),
            "generated_compose_dir": paths_cfg.get("generated_compose_dir", generated_compose_default),
            "generated_swiftui_dir": paths_cfg.get("generated_swiftui_dir", "generated/swiftui"),
            "swiftui_codegen_package_dir": paths_cfg.get("swiftui_codegen_package_dir", "pipeline/codegen-swiftui"),
        },
    }
    if not resolved["figma"]["file_key"]:
        raise ValueError("Missing Figma file key. Set --file-key or figma.file_key in config.")
    return resolved


def _load_figma_input(settings: dict[str, Any]) -> tuple[dict, FigmaApiClient | None]:
    figma = settings["figma"]
    figma_json = figma["figma_json"]
    if figma_json:
        payload = json.loads(Path(figma_json).read_text(encoding="utf-8"))
        return payload, None

    node_ids = figma["node_ids"]
    if not node_ids:
        raise ValueError("Provide Figma node ids via --node or figma.node_ids in config.")

    token = figma["token"] or os.getenv(figma["token_env"], "")
    if not token:
        raise ValueError(
            f"Provide figma_json or pass Figma token via --figma-token / ${figma['token_env']}"
        )
    client = FigmaApiClient(FigmaApiConfig(base_url=figma["base_url"], token=token))
    payload = client.fetch_nodes(file_key=figma["file_key"], node_ids=node_ids)
    return payload, client


def _resolve_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _remove_asset_refs(node: dict[str, Any]) -> None:
    node.pop("assetRef", None)
    for child in node.get("children", []):
        _remove_asset_refs(child)


def _write_asset_manifest_placeholder(reports_dir: Path, manifest: dict[str, Any]) -> None:
    (reports_dir / "asset-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _cleanup_outputs(root: Path, settings: dict[str, Any], logger: logging.Logger) -> None:
    if not settings["pipeline"]["clean_before_generate"]:
        logger.info("Output cleanup skipped by config (clean_before_generate=false).")
        return

    targets: list[Path] = [
        root / "generated",
    ]
    for raw in settings["pipeline"]["legacy_cleanup_paths"]:
        targets.append(_resolve_path(root, str(raw)))

    removed = 0
    for target in targets:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            removed += 1
            logger.info("Removed output directory: %s", target)
    if removed == 0:
        logger.info("No generated output directories to remove.")


def _run_native_swiftui_codegen(
    dsl: dict[str, Any],
    dsl_dir: Path,
    output_dir: Path,
    swiftui_codegen_package_dir: Path,
    swiftui_codegen_executable: str,
    swiftui_module_name: str,
    logger: logging.Logger,
) -> list[Path]:
    dsl_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    dsl_json_path = dsl_dir / "ui_dsl.json"
    dump_json(dsl, dsl_json_path)

    if not swiftui_codegen_package_dir.exists():
        raise ValueError(f"SwiftUI codegen package path does not exist: {swiftui_codegen_package_dir}")

    command = [
        "swift",
        "run",
        "--package-path",
        str(swiftui_codegen_package_dir),
        swiftui_codegen_executable,
        "--dsl-json",
        str(dsl_json_path),
        "--output-dir",
        str(output_dir),
        "--module-name",
        swiftui_module_name,
    ]
    logger.info("Running native SwiftUI codegen: %s", " ".join(command))
    result = subprocess.run(command, check=False, text=True, capture_output=True)
    if result.stdout:
        logger.info("swift run stdout:\n%s", result.stdout.strip())
    if result.stderr:
        logger.info("swift run stderr:\n%s", result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(f"SwiftUI native codegen failed with exit code {result.returncode}")

    return sorted(output_dir.rglob("*.swift"))


def _validate_dsl_mapping(
    dsl: dict[str, Any],
    ir: dict[str, Any],
    naming_config_path: Path,
    reports_dir: Path,
    fail_on_naming_error: bool,
    fail_on_naming_warning: bool,
) -> dict[str, Any]:
    contract = yaml.safe_load(naming_config_path.read_text(encoding="utf-8"))
    component_to_level = contract.get("component_to_level", {})

    naming_blocking_codes = {
        "NAMING_REGEX_MISMATCH",
        "UNKNOWN_LEVEL",
        "UNKNOWN_COMPONENT",
        "LEVEL_COMPONENT_MISMATCH",
        "UNKNOWN_VARIANT",
        "UNKNOWN_STATE",
        "UNKNOWN_ROLE",
    }

    naming_errors = [
        issue
        for issue in ir.get("issues", [])
        if issue.get("severity") == "error" and issue.get("code") in naming_blocking_codes
    ]
    naming_warnings = [
        issue
        for issue in ir.get("issues", [])
        if issue.get("severity") == "warning" and issue.get("code") in naming_blocking_codes
    ]

    dsl_issues: list[dict[str, Any]] = []
    for screen in dsl.get("screens", []):
        for node in _walk_dsl_nodes(screen):
            node_key = str(node.get("node", ""))
            parts = node_key.split("/")
            if len(parts) != 2:
                dsl_issues.append(
                    {
                        "severity": "error",
                        "code": "DSL_NODE_FORMAT_INVALID",
                        "nodeId": node.get("id"),
                        "message": f"Invalid DSL node key '{node_key}'",
                    }
                )
                continue
            level, component = parts
            expected_level = component_to_level.get(component)
            if expected_level is None:
                dsl_issues.append(
                    {
                        "severity": "error",
                        "code": "DSL_NODE_COMPONENT_UNKNOWN",
                        "nodeId": node.get("id"),
                        "message": f"Unknown DSL component '{component}' in node '{node_key}'",
                    }
                )
                continue
            if expected_level != level:
                dsl_issues.append(
                    {
                        "severity": "error",
                        "code": "DSL_NODE_LEVEL_MISMATCH",
                        "nodeId": node.get("id"),
                        "message": f"Component '{component}' expects level '{expected_level}', got '{level}'",
                    }
                )

    blocking = False
    if fail_on_naming_error and naming_errors:
        blocking = True
    if fail_on_naming_warning and naming_warnings:
        blocking = True
    if dsl_issues:
        blocking = True

    report = {
        "blocking": blocking,
        "namingErrors": len(naming_errors),
        "namingWarnings": len(naming_warnings),
        "dslIssues": len(dsl_issues),
        "namingErrorItems": naming_errors,
        "namingWarningItems": naming_warnings,
        "dslIssueItems": dsl_issues,
        "config": {
            "fail_on_naming_error": fail_on_naming_error,
            "fail_on_naming_warning": fail_on_naming_warning,
        },
    }
    (reports_dir / "dsl-validation-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if blocking:
        raise ValueError(
            "DSL validation failed. "
            f"namingErrors={len(naming_errors)}, namingWarnings={len(naming_warnings)}, dslIssues={len(dsl_issues)}. "
            "See generated/reports/dsl-validation-report.json"
        )
    return report


def _walk_dsl_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    stack = [node]
    out: list[dict[str, Any]] = []
    while stack:
        current = stack.pop()
        out.append(current)
        stack.extend(current.get("children", []))
    return out


def _configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@contextmanager
def _stage(logger: logging.Logger, stage_name: str):
    started = time.perf_counter()
    logger.info(">> %s started", stage_name)
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        logger.info("<< %s finished in %.2fs", stage_name, elapsed)


if __name__ == "__main__":
    main()
