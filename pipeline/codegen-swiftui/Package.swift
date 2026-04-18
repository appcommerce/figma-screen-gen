// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "SwiftUICodegen",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(name: "SwiftUICodegen", targets: ["SwiftUICodegen"]),
    ],
    targets: [
        .executableTarget(
            name: "SwiftUICodegen",
            path: "Sources/SwiftUICodegen"
        ),
    ]
)
