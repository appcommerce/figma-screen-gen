plugins {
    kotlin("jvm") version "2.0.21"
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.squareup:kotlinpoet:1.18.1")
    implementation("org.yaml:snakeyaml:2.2")
}

kotlin {
    jvmToolchain(17)
}

application {
    mainClass.set("compose.ComposePipelineMain")
}

tasks.register<JavaExec>("runDslToComposeGenerator") {
    group = "pipeline"
    description = "Run KotlinPoet DSL -> Compose generator directly"
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("compose.DslToComposeGeneratorKt")
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
