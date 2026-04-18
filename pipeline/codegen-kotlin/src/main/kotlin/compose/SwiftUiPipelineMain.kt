package compose

object SwiftUiPipelineMain {
    @JvmStatic
    fun main(args: Array<String>) {
        run(args)
    }

    fun run(args: Array<String>) {
        PipelineLauncher.run(
            args = args,
            target = "swiftui",
            swiftUiBackend = "native_swift",
        )
    }
}
