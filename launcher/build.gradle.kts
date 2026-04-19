plugins {
    kotlin("jvm") version "2.0.21"
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(project(":pipeline:codegen-kotlin"))
    implementation("org.yaml:snakeyaml:2.2")
}

kotlin {
    jvmToolchain(17)
}

application {
    mainClass.set("compose.ComposePipelineMain")
}

tasks.register<JavaExec>("runComposePipelineMain") {
    group = "pipeline"
    description = "Run Compose pipeline launcher main"
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("compose.ComposePipelineMain")
}

tasks.register<JavaExec>("runSwiftUiPipelineMain") {
    group = "pipeline"
    description = "Run SwiftUI pipeline launcher main"
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("compose.SwiftUiPipelineMain")
}
