plugins {
    kotlin("jvm") version "2.0.21"
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

tasks.register<JavaExec>("runDslToComposeGenerator") {
    group = "pipeline"
    description = "Run KotlinPoet DSL -> Compose generator directly"
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("compose.DslToComposeGeneratorKt")
}
