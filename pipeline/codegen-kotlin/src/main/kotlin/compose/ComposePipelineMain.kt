package compose

object ComposePipelineMain {
    @JvmStatic
    fun main(args: Array<String>) {
        run(args)
    }

    fun run(args: Array<String>) {
        PipelineLauncher.run(args = args, target = "compose")
    }
}
