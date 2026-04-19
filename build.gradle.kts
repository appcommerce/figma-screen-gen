import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.Delete

plugins {
    base
}

val pythonBin = providers.gradleProperty("pythonBin").orElse(".venv/bin/python")
val figmaConfig = providers.gradleProperty("figmaConfig").orElse("pipeline/config/pipeline-config.yaml")
val figmaFileKey = providers.gradleProperty("figmaFileKey")
val figmaNodeId = providers.gradleProperty("figmaNodeId")
val figmaJson = providers.gradleProperty("figmaJson")
val outRoot = providers.gradleProperty("outRoot").orElse(project.layout.projectDirectory.asFile.absolutePath)
val packageName = providers.gradleProperty("packageName").orElse("com.example.generated")
val target = providers.gradleProperty("target").orElse("compose")
val swiftUiBackend = providers.gradleProperty("swiftUiBackend").orElse("native_swift")
val refreshVenv = providers.gradleProperty("refreshVenv").orElse("false")

val currentGeneratedRoot = project.layout.projectDirectory.dir("generated")
val legacyGeneratedDirs = listOf(
    "pipeline/generated_ir",
    "pipeline/generated_dsl",
    "pipeline/reports",
    "pipeline/assets",
    "pipeline/snapshots",
    "app/src/main/java/com/example/generated",
)

tasks.register<Delete>("pipelineCleanGenerated") {
    group = "pipeline"
    description = "Clean current and legacy generated artifacts before regeneration"
    delete(currentGeneratedRoot)
    delete(legacyGeneratedDirs.map { project.layout.projectDirectory.dir(it) })
}

tasks.register<Exec>("pipelineBootstrap") {
    group = "pipeline"
    description = "Create venv and install pipeline deps (skips when already prepared)"
    workingDir = project.projectDir
    onlyIf {
        val refresh = refreshVenv.get().toBooleanStrictOrNull() ?: false
        val marker = project.layout.projectDirectory.file(".venv/.pipeline_deps_installed").asFile
        refresh || !marker.exists()
    }
    commandLine(
        "sh",
        "-c",
        "python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]' && touch .venv/.pipeline_deps_installed"
    )
}

tasks.register<Exec>("pipelineGenerateUi") {
    group = "pipeline"
    description = "Clean and run Figma -> JSON -> DSL (with validation) pipeline"
    dependsOn("pipelineBootstrap", "pipelineCleanGenerated")
    workingDir = project.projectDir

    doFirst {
        val args = mutableListOf(
            pythonBin.get(),
            "-m",
            "pipeline.src.generate_ui",
            "--config",
            figmaConfig.get(),
            "--out-root",
            outRoot.get(),
            "--target",
            target.get(),
        )
        if (target.get() == "swiftui") {
            args += listOf("--swiftui-backend", swiftUiBackend.get())
        }

        if (figmaFileKey.isPresent) {
            args += listOf("--file-key", figmaFileKey.get())
        }
        if (packageName.isPresent) {
            args += listOf("--package-name", packageName.get())
        }
        if (figmaJson.isPresent) {
            args += listOf("--figma-json", figmaJson.get())
        }
        if (figmaNodeId.isPresent) {
            args += listOf("--node", figmaNodeId.get())
        }
        commandLine(args)
    }
}

tasks.register("pipelineRunAll") {
    group = "pipeline"
    description = "Bootstrap and run full UI pipeline"
    dependsOn("pipelineGenerateUi", "pipelineComposeCodegen")
}

tasks.register<JavaExec>("pipelineComposeCodegen") {
    group = "pipeline"
    description = "Run KotlinPoet Compose codegen from generated DSL"
    dependsOn(":pipeline:codegen-kotlin:classes", "pipelineGenerateUi")
    onlyIf { target.get() == "compose" }
    classpath = project(":pipeline:codegen-kotlin")
        .extensions
        .getByType(org.gradle.api.tasks.SourceSetContainer::class.java)
        .named("main")
        .get()
        .runtimeClasspath
    mainClass.set("compose.DslToComposeGeneratorKt")

    doFirst {
        val dslPath = project.layout.projectDirectory.file("generated/dsl/ui_dsl.yaml").asFile.absolutePath
        val outputDir = project.layout.projectDirectory.dir("generated/compose/src/main/java").asFile.absolutePath
        args(dslPath, outputDir, packageName.get())
    }
}

tasks.register<Exec>("pipelineGenerateComposeUi") {
    group = "pipeline"
    description = "Clean and run Figma -> JSON -> DSL -> Compose pipeline"
    dependsOn("pipelineBootstrap", "pipelineCleanGenerated")
    workingDir = project.projectDir

    doFirst {
        val args = mutableListOf(
            pythonBin.get(),
            "-m",
            "pipeline.src.generate_ui",
            "--config",
            figmaConfig.get(),
            "--out-root",
            outRoot.get(),
            "--target",
            "compose",
        )
        if (figmaFileKey.isPresent) {
            args += listOf("--file-key", figmaFileKey.get())
        }
        if (packageName.isPresent) {
            args += listOf("--package-name", packageName.get())
        }
        if (figmaJson.isPresent) {
            args += listOf("--figma-json", figmaJson.get())
        }
        if (figmaNodeId.isPresent) {
            args += listOf("--node", figmaNodeId.get())
        }
        commandLine(args)
    }
}

tasks.register<Exec>("pipelineGenerateSwiftUi") {
    group = "pipeline"
    description = "Clean and run Figma -> JSON -> DSL -> native SwiftUI pipeline"
    dependsOn("pipelineBootstrap", "pipelineCleanGenerated")
    workingDir = project.projectDir

    doFirst {
        val args = mutableListOf(
            pythonBin.get(),
            "-m",
            "pipeline.src.generate_ui",
            "--config",
            figmaConfig.get(),
            "--out-root",
            outRoot.get(),
            "--target",
            "swiftui",
            "--swiftui-backend",
            swiftUiBackend.get(),
        )
        if (figmaFileKey.isPresent) {
            args += listOf("--file-key", figmaFileKey.get())
        }
        if (packageName.isPresent) {
            args += listOf("--package-name", packageName.get())
        }
        if (figmaJson.isPresent) {
            args += listOf("--figma-json", figmaJson.get())
        }
        if (figmaNodeId.isPresent) {
            args += listOf("--node", figmaNodeId.get())
        }
        commandLine(args)
    }
}

tasks.register("pipelineRunComposeMain") {
    group = "pipeline"
    description = "Run compose.ComposePipelineMain from codegen-kotlin module"
    dependsOn(":pipeline:codegen-kotlin:runComposePipelineMain")
}

tasks.register("pipelineRunSwiftUiMain") {
    group = "pipeline"
    description = "Run compose.SwiftUiPipelineMain from codegen-kotlin module"
    dependsOn(":pipeline:codegen-kotlin:runSwiftUiPipelineMain")
}

tasks.register<Exec>("pipelineValidateDsl") {
    group = "pipeline"
    description = "Run pipeline until DSL validation (without Compose codegen)"
    dependsOn("pipelineBootstrap", "pipelineCleanGenerated")
    workingDir = project.projectDir

    doFirst {
        val args = mutableListOf(
            pythonBin.get(),
            "-m",
            "pipeline.src.generate_ui",
            "--config",
            figmaConfig.get(),
            "--out-root",
            outRoot.get(),
            "--validate-only",
        )

        if (figmaFileKey.isPresent) {
            args += listOf("--file-key", figmaFileKey.get())
        }
        if (packageName.isPresent) {
            args += listOf("--package-name", packageName.get())
        }
        if (figmaJson.isPresent) {
            args += listOf("--figma-json", figmaJson.get())
        }
        if (figmaNodeId.isPresent) {
            args += listOf("--node", figmaNodeId.get())
        }
        commandLine(args)
    }
}
