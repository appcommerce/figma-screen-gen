# Figma -> Compose/SwiftUI Pipeline

Production-oriented scaffolding for converting Figma nodes into:

1. normalized JSON IR
2. YAML DSL
3. generated Jetpack Compose Kotlin stubs or SwiftUI stubs (native Swift backend)

Also includes asset export/conversion pipeline and quality gates.

## Quick start

```bash
python -m pip install -e ".[dev]"
cp .env.example .env
# set FIGMA_TOKEN in .env when using API mode
python -m pipeline.src.generate_ui --help
```

## Command

```bash
python -m pipeline.src.generate_ui \
  --config pipeline/config/pipeline-config.yaml \
  --figma-json pipeline/tests/fixtures/sample_figma_nodes.json \
  --target compose \
  --log-level INFO \
  --out-root .
```

### Run with Figma REST API (production mode)

```bash
export FIGMA_TOKEN=your_figma_personal_access_token
python -m pipeline.src.generate_ui \
  --config pipeline/config/pipeline-config.yaml \
  --target compose \
  --out-root .
```

`FIGMA_TOKEN` is also loaded automatically from project `.env` (if present).

Generate SwiftUI with native Swift codegen:

```bash
python -m pipeline.src.generate_ui \
  --config pipeline/config/pipeline-config.yaml \
  --figma-json pipeline/tests/fixtures/sample_figma_nodes.json \
  --target swiftui \
  --swiftui-backend native_swift \
  --out-root .
```

All Figma constants are in:

- `pipeline/config/pipeline-config.yaml`

You can still override config values from CLI:

```bash
python -m pipeline.src.generate_ui \
  --config pipeline/config/pipeline-config.yaml \
  --file-key another_file_key \
  --node 123:456
```

## Gradle pipeline tasks

Run full pipeline as sequential Gradle tasks (target selectable via `-Ptarget=compose|swiftui`):

```bash
./gradlew pipelineRunAll \
  -PfigmaConfig=pipeline/config/pipeline-config.yaml \
  -Ptarget=compose
```

Run only DSL validation (skip Compose codegen):

```bash
./gradlew pipelineValidateDsl \
  -PfigmaConfig=pipeline/config/pipeline-config.yaml
```

The pipeline keeps artifacts inside `generated/` and does not publish/copy into `app/` automatically.
Before generation it automatically cleans both `generated/` and legacy generated folders.

Run from local fixture JSON:

```bash
./gradlew pipelineRunAll \
  -PfigmaConfig=pipeline/config/pipeline-config.yaml \
  -PfigmaJson=pipeline/tests/fixtures/sample_figma_nodes.json \
  -PfigmaFileKey=demo_file \
  -Ptarget=swiftui
```

Dedicated tasks:

```bash
./gradlew pipelineGenerateComposeUi -PfigmaJson=pipeline/tests/fixtures/sample_figma_nodes.json -PfigmaFileKey=demo_file
./gradlew pipelineGenerateSwiftUi -PfigmaJson=pipeline/tests/fixtures/sample_figma_nodes.json -PfigmaFileKey=demo_file
```

Compose target:

```bash
./gradlew pipelineGenerateComposeUi \
  -PfigmaConfig=pipeline/config/pipeline-config.yaml \
  -PfigmaJson=pipeline/tests/fixtures/sample_figma_nodes.json \
  -PfigmaFileKey=demo_file
```

SwiftUI target:

```bash
./gradlew pipelineGenerateSwiftUi \
  -PfigmaConfig=pipeline/config/pipeline-config.yaml \
  -PfigmaJson=pipeline/tests/fixtures/sample_figma_nodes.json \
  -PfigmaFileKey=demo_file
```

Useful properties:

- `-PpythonBin=.venv/bin/python`
- `-PfigmaConfig=pipeline/config/pipeline-config.yaml`
- `-PoutRoot=/Users/ruslan/Project/figma-code`
- `-PpackageName=com.example.generated`
- `-Ptarget=compose|swiftui`
- `-PswiftUiBackend=native_swift`
- `-PrefreshVenv=true` (force reinstall dependencies)

Pipeline logs every stage with timings directly in Gradle output (download, normalize, assets, DSL, codegen, quality checks).
If naming mapping does not match, pipeline fails before code generation and writes report:
`generated/reports/dsl-validation-report.json`.

## Start from Kotlin main

You can run separate mains from IDE:

- `compose.ComposePipelineMain` (Compose target)
- `compose.SwiftUiPipelineMain` (SwiftUI target via native Swift backend)

Or from Gradle:

```bash
./gradlew pipelineRunComposeMain
./gradlew pipelineRunSwiftUiMain
```

Both mains accept the same CLI args:

```bash
--config pipeline/config/pipeline-config.yaml
```

## Where generation happens

- Pipeline orchestration: `pipeline/src/generate_ui.py`
- Compose code generation: `pipeline/src/compose_generator.py` in `ComposeGenerator.generate(...)`
- Native SwiftUI code generation: `pipeline/codegen-swiftui/Sources/SwiftUICodegen/main.swift`

## SwiftUI DSL mapping

Native SwiftUI generator maps DSL semantic nodes to SwiftUI primitives (not Android widgets):

- `screen/page` -> `ScrollView + VStack`
- `screen/bottomSheet` -> material `VStack` container
- `screen/dialog` -> card-like `VStack` with shadow
- `layout/column|row|box|grid` -> `VStack|HStack|ZStack|LazyVGrid`
- `content/text|icon|image` -> `Text|Image|Image`
- input/data/feedback components (`checkbox`, `textField`, `list`, `button`, `progress*`, etc.) -> corresponding SwiftUI controls with deterministic fallbacks

Supported DSL props include `widthDp`, `heightDp`, `xDp`, `yDp`, `padding.*`, `spacingDp`, `tokenRef`, `testTag`, `contentDescription`, `resourceName`.

## Compose DSL mapping

Compose generator now maps the same semantic DSL node families used by SwiftUI generation:

- screen containers: `screen/page|bottomSheet|dialog`
- layouts: `layout/column|row|box|grid|stack|constraint|flow`
- content: `content/text|icon|image|illustration|video|lottie`
- components/feedback: lists, inputs, actions, progress, badges, overlays, feedback states

Supported Compose-side props include `widthDp`, `heightDp`, `xDp`, `yDp`, `padding.*`, `spacingDp`, `tokenRef`, `contentDescription`, `testTag`, `resourceName`.

## Generated artifacts layout

All stage outputs are stored under `generated/`:

- `generated/ir/ui_ir.json`
- `generated/dsl/ui_dsl.yaml`
- `generated/reports/*.json`
- `generated/assets/svg/*.svg`
- `generated/resources/drawable/*.xml`
- `generated/compose/src/main/java/...`
- `generated/resources/ios/Assets.xcassets/**`
- `generated/swiftui/**`
# figma-screen-gen
