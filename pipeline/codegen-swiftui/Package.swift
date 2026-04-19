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
    dependencies: [
        .package(url: "https://github.com/swiftlang/swift-syntax.git", from: "509.0.0"),
    ],
    targets: [
        .executableTarget(
            name: "SwiftUICodegen",
            dependencies: [
                .product(name: "SwiftSyntax", package: "swift-syntax"),
                .product(name: "SwiftSyntaxBuilder", package: "swift-syntax"),
            ],
            path: "Sources/SwiftUICodegen"
        ),
    ]
)
