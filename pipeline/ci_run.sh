#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python -m pipeline.src.generate_ui \
  --figma-json pipeline/tests/fixtures/sample_figma_nodes.json \
  --file-key ci_demo \
  --target compose \
  --out-root .

swift build --package-path pipeline/codegen-swiftui

python -m pipeline.src.generate_ui \
  --figma-json pipeline/tests/fixtures/sample_figma_nodes.json \
  --file-key ci_demo \
  --target swiftui \
  --swiftui-backend native_swift \
  --out-root .

python -m pytest -q pipeline/tests
