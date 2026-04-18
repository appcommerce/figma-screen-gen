package compose

import java.io.File

internal object PipelineLauncher {
    fun run(args: Array<String>, target: String, swiftUiBackend: String? = null) {
        val cli = parseArgs(args)
        val root = findProjectRoot(File(System.getProperty("user.dir")))
        val pythonBin = cli["python-bin"] ?: System.getenv("PIPELINE_PYTHON_BIN") ?: "${root.absolutePath}/.venv/bin/python"
        val configPath = cli["config"] ?: "pipeline/config/pipeline-config.yaml"
        val packageName = cli["package-name"]
        val outRoot = cli["out-root"] ?: root.absolutePath
        val fileKey = cli["file-key"]
        val figmaJson = cli["figma-json"]
        val nodeId = cli["node"]

        val command = mutableListOf(
            pythonBin,
            "-m",
            "pipeline.src.generate_ui",
            "--config",
            configPath,
            "--out-root",
            outRoot,
            "--target",
            target,
        )
        if (swiftUiBackend != null) {
            command += listOf("--swiftui-backend", swiftUiBackend)
        }
        if (fileKey != null) {
            command += listOf("--file-key", fileKey)
        }
        if (packageName != null) {
            command += listOf("--package-name", packageName)
        }
        if (figmaJson != null) {
            command += listOf("--figma-json", figmaJson)
        }
        if (nodeId != null) {
            command += listOf("--node", nodeId)
        }

        val process = ProcessBuilder(command)
            .directory(root)
            .inheritIO()
            .start()
        val code = process.waitFor()
        if (code != 0) {
            error("Pipeline process failed with exit code $code")
        }
    }

    private fun parseArgs(args: Array<String>): Map<String, String> {
        val map = linkedMapOf<String, String>()
        var i = 0
        while (i < args.size) {
            val key = args[i]
            if (!key.startsWith("--")) {
                i += 1
                continue
            }
            if (i + 1 >= args.size) {
                error("Missing value for $key")
            }
            map[key.removePrefix("--")] = args[i + 1]
            i += 2
        }
        return map
    }

    private fun findProjectRoot(start: File): File {
        var current: File? = start.absoluteFile
        while (current != null) {
            if (File(current, "pyproject.toml").exists() && File(current, "pipeline").exists()) {
                return current
            }
            current = current.parentFile
        }
        error("Cannot locate project root from ${start.absolutePath}")
    }
}
