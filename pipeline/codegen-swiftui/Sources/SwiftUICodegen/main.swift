import Foundation
import SwiftSyntax
import SwiftSyntaxBuilder

struct CliOptions {
    let dslJsonPath: String
    let outputDir: String
    let moduleName: String
}

enum CliError: Error, CustomStringConvertible {
    case missingArgument(String)
    case invalidFormat(String)

    var description: String {
        switch self {
        case .missingArgument(let arg):
            return "Missing required argument: \(arg)"
        case .invalidFormat(let message):
            return "Invalid input format: \(message)"
        }
    }
}

func parseArgs(_ args: [String]) throws -> CliOptions {
    func required(_ key: String, in map: [String: String]) throws -> String {
        guard let value = map[key], !value.isEmpty else {
            throw CliError.missingArgument("--\(key)")
        }
        return value
    }

    var values: [String: String] = [:]
    var idx = 0
    while idx < args.count {
        let arg = args[idx]
        if !arg.hasPrefix("--") {
            idx += 1
            continue
        }
        let key = String(arg.dropFirst(2))
        guard idx + 1 < args.count else {
            throw CliError.missingArgument(arg)
        }
        values[key] = args[idx + 1]
        idx += 2
    }

    let dslJsonPath = try required("dsl-json", in: values)
    let outputDir = try required("output-dir", in: values)
    let moduleName = values["module-name"] ?? "GeneratedSwiftUI"
    return CliOptions(dslJsonPath: dslJsonPath, outputDir: outputDir, moduleName: moduleName)
}

func toDictionary(_ value: Any?) -> [String: Any] {
    value as? [String: Any] ?? [:]
}

func toArray(_ value: Any?) -> [[String: Any]] {
    value as? [[String: Any]] ?? []
}

func toString(_ value: Any?) -> String {
    value as? String ?? ""
}

func toDouble(_ value: Any?) -> Double? {
    if let x = value as? Double {
        return x
    }
    if let x = value as? Int {
        return Double(x)
    }
    if let x = value as? NSNumber {
        return x.doubleValue
    }
    return nil
}

func toInt(_ value: Any?) -> Int? {
    if let x = value as? Int {
        return x
    }
    if let x = value as? Double {
        return Int(x)
    }
    if let x = value as? NSNumber {
        return x.intValue
    }
    return nil
}

func sanitizeSwiftString(_ input: String) -> String {
    input
        .replacingOccurrences(of: "\\", with: "\\\\")
        .replacingOccurrences(of: "\"", with: "\\\"")
}

func pascalCase(_ input: String) -> String {
    let separators = CharacterSet.alphanumerics.inverted
    let chunks = input
        .components(separatedBy: separators)
        .filter { !$0.isEmpty }
    if chunks.isEmpty {
        return "Unknown"
    }
    return chunks.map { chunk in
        guard let first = chunk.first else { return chunk }
        return String(first).uppercased() + chunk.dropFirst()
    }.joined()
}

enum BodySpec {
    case none
    case children([ViewSpec])
    case raw([String])
}

struct ViewSpec {
    let head: String
    let body: BodySpec
    let modifiers: [String]
}

func textLiteral(node: [String: Any], props: [String: Any]) -> String {
    let text = toString(props["text"]).isEmpty ? toString(node["name"]) : toString(props["text"])
    return sanitizeSwiftString(text.isEmpty ? "Untitled" : text)
}

func resolvedLayout(nodeKey: String, props: [String: Any]) -> String {
    let layout = toString(props["layout"])
    if nodeKey == "layout/column" || layout == "column" {
        return "column"
    }
    if nodeKey == "layout/row" || layout == "row" {
        return "row"
    }
    if nodeKey == "layout/grid" || layout == "grid" {
        return "grid"
    }
    return "box"
}

func buildModifierCalls(props: [String: Any]) -> [String] {
    var calls: [String] = []
    let width = toDouble(props["widthDp"])
    let height = toDouble(props["heightDp"])
    let offsetX = toDouble(props["xDp"]) ?? 0
    let offsetY = toDouble(props["yDp"]) ?? 0

    if let width, let height {
        calls.append("frame(width: \(width), height: \(height))")
    } else if let width {
        calls.append("frame(width: \(width))")
    } else if let height {
        calls.append("frame(height: \(height))")
    }

    let padding = toDictionary(props["padding"])
    if !padding.isEmpty {
        let top = toDouble(padding["topDp"]) ?? 0
        let left = toDouble(padding["leftDp"]) ?? 0
        let bottom = toDouble(padding["bottomDp"]) ?? 0
        let right = toDouble(padding["rightDp"]) ?? 0
        calls.append("padding(EdgeInsets(top: \(top), leading: \(left), bottom: \(bottom), trailing: \(right)))")
    }

    let tokenRef = toString(props["tokenRef"])
    if tokenRef.hasPrefix("#"), tokenRef.count == 7 {
        let hex = sanitizeSwiftString(tokenRef)
        calls.append("background(Color(hex: \"\(hex)\"))")
    }

    if offsetX != 0 || offsetY != 0 {
        calls.append("offset(x: \(offsetX), y: \(offsetY))")
    }

    let testTag = sanitizeSwiftString(toString(props["testTag"]))
    if !testTag.isEmpty {
        calls.append("accessibilityIdentifier(\"\(testTag)\")")
    }
    let contentDescription = sanitizeSwiftString(toString(props["contentDescription"]))
    if !contentDescription.isEmpty {
        calls.append("accessibilityLabel(\"\(contentDescription)\")")
    }

    return calls
}

func emitNodeSpec(_ node: [String: Any]) -> ViewSpec {
    let nodeKey = toString(node["node"])
    let props = toDictionary(node["props"])
    let children = toArray(node["children"])
    let childSpecs = children.map(emitNodeSpec)
    let spacing = toInt(props["spacingDp"]) ?? 0
    let text = textLiteral(node: node, props: props)
    let nodeNameFallback = toString(node["name"]).isEmpty ? "placeholder" : toString(node["name"])
    let resourceCandidate = toString(props["resourceName"]).isEmpty ? nodeNameFallback : toString(props["resourceName"])
    let resourceName = sanitizeSwiftString(resourceCandidate)
    let checked = toString(node["state"]) == "checked" ? "true" : "false"
    let layoutKind = resolvedLayout(nodeKey: nodeKey, props: props)
    let modifiers = buildModifierCalls(props: props)

    if nodeKey == "layout/column" || nodeKey == "layout/stack" || (nodeKey == "layout/constraint" && layoutKind == "column") || (nodeKey == "layout/flow" && layoutKind == "column") {
        return ViewSpec(
            head: "VStack(alignment: .leading, spacing: \(spacing))",
            body: .children(childSpecs),
            modifiers: modifiers
        )
    }
    if nodeKey == "layout/row" || (nodeKey == "layout/constraint" && layoutKind == "row") || (nodeKey == "layout/flow" && layoutKind == "row") {
        return ViewSpec(
            head: "HStack(alignment: .center, spacing: \(spacing))",
            body: .children(childSpecs),
            modifiers: modifiers
        )
    }
    if nodeKey == "layout/grid" || layoutKind == "grid" {
        return ViewSpec(
            head: "LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: \(spacing))",
            body: .children(childSpecs),
            modifiers: modifiers
        )
    }
    if nodeKey == "layout/box" || nodeKey == "layout/constraint" || nodeKey == "layout/flow" {
        return ViewSpec(
            head: "ZStack",
            body: .children(childSpecs),
            modifiers: modifiers
        )
    }

    switch nodeKey {
    case "screen/page":
        return ViewSpec(
            head: "ScrollView",
            body: .children(
                [
                    ViewSpec(
                        head: "VStack(alignment: .leading, spacing: \(spacing))",
                        body: .children(childSpecs),
                        modifiers: []
                    )
                ]
            ),
            modifiers: modifiers
        )
    case "screen/bottomSheet":
        return ViewSpec(
            head: "VStack(alignment: .leading, spacing: \(spacing))",
            body: .children(childSpecs),
            modifiers: ["padding(16)", "background(.ultraThinMaterial)", "clipShape(RoundedRectangle(cornerRadius: 16))"] + modifiers
        )
    case "screen/dialog":
        return ViewSpec(
            head: "VStack(alignment: .leading, spacing: \(spacing))",
            body: .children(childSpecs),
            modifiers: ["padding(20)", "background(Color.white)", "clipShape(RoundedRectangle(cornerRadius: 12))", "shadow(radius: 8)"] + modifiers
        )
    case "content/text":
        return ViewSpec(
            head: "Text(\"\(text)\")",
            body: .none,
            modifiers: modifiers
        )
    case "content/icon", "content/image", "content/illustration":
        return ViewSpec(
            head: "Image(\"\(resourceName)\")",
            body: .none,
            modifiers: modifiers
        )
    case "content/video", "content/lottie":
        return ViewSpec(
            head: "ZStack",
            body: .raw(
                [
                    "RoundedRectangle(cornerRadius: 8).fill(Color.gray.opacity(0.2))",
                    "Text(\"Media: \(text)\")",
                ]
            ),
            modifiers: modifiers
        )
    case "component/listVertical":
        return ViewSpec(
            head: "ScrollView",
            body: .children(
                [
                    ViewSpec(
                        head: "LazyVStack(alignment: .leading, spacing: \(spacing))",
                        body: .children(childSpecs),
                        modifiers: []
                    )
                ]
            ),
            modifiers: modifiers
        )
    case "component/listHorizontal":
        return ViewSpec(
            head: "ScrollView(.horizontal, showsIndicators: false)",
            body: .children(
                [
                    ViewSpec(
                        head: "LazyHStack(alignment: .center, spacing: \(spacing))",
                        body: .children(childSpecs),
                        modifiers: []
                    )
                ]
            ),
            modifiers: modifiers
        )
    case "component/listItem", "component/card":
        return ViewSpec(
            head: "VStack(alignment: .leading, spacing: \(spacing))",
            body: .children(childSpecs),
            modifiers: ["padding(12)", "background(Color.gray.opacity(0.08))", "clipShape(RoundedRectangle(cornerRadius: 10))"] + modifiers
        )
    case "component/button", "component/fab", "component/iconButton", "component/chip", "component/toggleChip", "component/segmentedControl":
        let content: [String]
        if resourceName != "placeholder" {
            content = ["Image(\"\(resourceName)\")"]
        } else {
            content = ["Text(\"\(text)\")"]
        }
        return ViewSpec(
            head: "Button(action: {})",
            body: .raw(content),
            modifiers: ["buttonStyle(.borderedProminent)"] + modifiers
        )
    case "component/textField", "component/searchField":
        return ViewSpec(
            head: "TextField(\"\(text)\", text: .constant(\"\"))",
            body: .none,
            modifiers: modifiers
        )
    case "component/passwordField":
        return ViewSpec(
            head: "SecureField(\"\(text)\", text: .constant(\"\"))",
            body: .none,
            modifiers: modifiers
        )
    case "component/checkbox", "component/switch", "component/radio":
        return ViewSpec(
            head: "Toggle(isOn: .constant(\(checked)))",
            body: .raw(["Text(\"\(text)\")"]),
            modifiers: modifiers
        )
    case "component/slider", "component/rangeSlider":
        return ViewSpec(
            head: "Slider(value: .constant(0.5), in: 0...1)",
            body: .none,
            modifiers: modifiers
        )
    case "component/stepper":
        return ViewSpec(
            head: "Stepper(\"\(text)\", value: .constant(0), in: 0...100)",
            body: .none,
            modifiers: modifiers
        )
    case "component/datePicker":
        return ViewSpec(
            head: "DatePicker(\"\(text)\", selection: .constant(Date()), displayedComponents: .date)",
            body: .none,
            modifiers: modifiers
        )
    case "component/timePicker":
        return ViewSpec(
            head: "DatePicker(\"\(text)\", selection: .constant(Date()), displayedComponents: .hourAndMinute)",
            body: .none,
            modifiers: modifiers
        )
    case "component/dropdown":
        return ViewSpec(
            head: "Picker(\"\(text)\", selection: .constant(\"Option 1\"))",
            body: .raw(["Text(\"Option 1\").tag(\"Option 1\")", "Text(\"Option 2\").tag(\"Option 2\")"]),
            modifiers: modifiers
        )
    case "component/table":
        return ViewSpec(
            head: "VStack(alignment: .leading, spacing: \(spacing))",
            body: .children(childSpecs),
            modifiers: ["overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.gray.opacity(0.3), lineWidth: 1))"] + modifiers
        )
    case "component/badge":
        return ViewSpec(
            head: "Text(\"\(text)\")",
            body: .none,
            modifiers: ["font(.caption)", "padding(.horizontal, 8)", "padding(.vertical, 4)", "background(Color.gray.opacity(0.2))", "clipShape(Capsule())"] + modifiers
        )
    case "component/avatar":
        return ViewSpec(
            head: "Circle().fill(Color.gray.opacity(0.3)).overlay(Text(\"\(String(text.prefix(2)))\"))",
            body: .none,
            modifiers: modifiers
        )
    case "component/progressLinear":
        return ViewSpec(
            head: "ProgressView(value: 0.5)",
            body: .none,
            modifiers: modifiers
        )
    case "component/progressCircular", "feedback/loading":
        return ViewSpec(
            head: "ProgressView()",
            body: .none,
            modifiers: modifiers
        )
    case "component/divider":
        return ViewSpec(
            head: "Divider()",
            body: .none,
            modifiers: modifiers
        )
    case "component/snackbar", "component/toast", "component/tooltip", "component/banner", "feedback/error", "feedback/empty", "feedback/success", "feedback/offline":
        return ViewSpec(
            head: "Text(\"\(text)\")",
            body: .none,
            modifiers: ["padding(10)", "background(Color.gray.opacity(0.15))", "clipShape(RoundedRectangle(cornerRadius: 8))"] + modifiers
        )
    case "raw/frame":
        return ViewSpec(
            head: "Group",
            body: .children(childSpecs),
            modifiers: modifiers
        )
    default:
        return ViewSpec(
            head: "VStack(alignment: .leading, spacing: \(spacing))",
            body: .children(
                [
                    ViewSpec(head: "Text(\"Unsupported node: \(sanitizeSwiftString(nodeKey))\")", body: .none, modifiers: []),
                ] + childSpecs
            ),
            modifiers: modifiers
        )
    }
}

func renderViewSpec(_ spec: ViewSpec, indent: Int) -> String {
    let space = String(repeating: "    ", count: indent)
    var lines: [String] = ["\(space)\(spec.head)"]

    switch spec.body {
    case .none:
        break
    case .children(let children):
        lines[0] += " {"
        lines.append(contentsOf: children.map { renderViewSpec($0, indent: indent + 1) })
        lines.append("\(space)}")
    case .raw(let rawLines):
        lines[0] += " {"
        for raw in rawLines {
            lines.append("\(String(repeating: "    ", count: indent + 1))\(raw)")
        }
        lines.append("\(space)}")
    }

    for modifier in spec.modifiers {
        lines.append("\(space).\(modifier)")
    }
    return lines.joined(separator: "\n")
}

func buildScreenFile(moduleName: String, screenName: String, node: [String: Any]) -> String {
    let bodySpec = emitNodeSpec(node)
    let body = renderViewSpec(bodySpec, indent: 2)
    let source: SourceFileSyntax =
        """
        import SwiftUI

        // DO NOT EDIT: generated by pipeline
        public struct \(raw: screenName)Screen: View {
            public init() {}

            public var body: some View {
        \(raw: body)
            }
        }

        private extension Color {
            init(hex: String) {
                let cleaned = hex.replacingOccurrences(of: "#", with: "")
                guard cleaned.count == 6, let value = Int(cleaned, radix: 16) else {
                    self = .clear
                    return
                }
                self = Color(
                    red: Double((value >> 16) & 0xFF) / 255.0,
                    green: Double((value >> 8) & 0xFF) / 255.0,
                    blue: Double(value & 0xFF) / 255.0
                )
            }
        }
        """
    return source.formatted().description
}

func buildPreviewFile(moduleName: String, screenName: String) -> String {
    let source: SourceFileSyntax =
        """
        import SwiftUI

        // DO NOT EDIT: generated by pipeline
        #Preview {
            \(raw: screenName)Screen()
        }
        """
    return source.formatted().description
}

func writeRootContentsIfNeeded(outputDir: URL) throws {
    let fm = FileManager.default
    if !fm.fileExists(atPath: outputDir.path) {
        try fm.createDirectory(at: outputDir, withIntermediateDirectories: true)
    }
}

@main
struct SwiftUICodegenMain {
    static func main() {
        do {
            let options = try parseArgs(Array(CommandLine.arguments.dropFirst()))
            let dslUrl = URL(fileURLWithPath: options.dslJsonPath)
            let raw = try Data(contentsOf: dslUrl)
            let payload = try JSONSerialization.jsonObject(with: raw, options: []) as? [String: Any]
            guard let payload else {
                throw CliError.invalidFormat("Top-level JSON must be object")
            }
            let screens = toArray(payload["screens"])

            let outputRoot = URL(fileURLWithPath: options.outputDir)
            let screensDir = outputRoot.appendingPathComponent("screens", isDirectory: true)
            let previewsDir = outputRoot.appendingPathComponent("previews", isDirectory: true)

            try writeRootContentsIfNeeded(outputDir: screensDir)
            try writeRootContentsIfNeeded(outputDir: previewsDir)

            for screen in screens {
                let rawScreenName = toString(screen["name"]).isEmpty ? "Screen" : toString(screen["name"])
                let screenName = pascalCase(rawScreenName)
                let screenFile = screensDir.appendingPathComponent("\(screenName)Screen.swift")
                let previewFile = previewsDir.appendingPathComponent("\(screenName)Preview.swift")
                let screenSource = buildScreenFile(moduleName: options.moduleName, screenName: screenName, node: screen)
                let previewSource = buildPreviewFile(moduleName: options.moduleName, screenName: screenName)
                try screenSource.write(to: screenFile, atomically: true, encoding: .utf8)
                try previewSource.write(to: previewFile, atomically: true, encoding: .utf8)
                print("GENERATED \(screenFile.path)")
                print("GENERATED \(previewFile.path)")
            }
        } catch {
            fputs("SwiftUICodegen failed: \(error)\n", stderr)
            exit(1)
        }
    }
}
