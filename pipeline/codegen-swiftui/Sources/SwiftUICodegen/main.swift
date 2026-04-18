import Foundation

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

func emitModifierChain(props: [String: Any], baseIndent: String) -> String {
    var lines: [String] = []
    let width = toDouble(props["widthDp"])
    let height = toDouble(props["heightDp"])
    let offsetX = toDouble(props["xDp"]) ?? 0
    let offsetY = toDouble(props["yDp"]) ?? 0

    if let width, let height {
        lines.append("\(baseIndent).frame(width: \(width), height: \(height))")
    } else if let width {
        lines.append("\(baseIndent).frame(width: \(width))")
    } else if let height {
        lines.append("\(baseIndent).frame(height: \(height))")
    }

    let padding = toDictionary(props["padding"])
    if !padding.isEmpty {
        let top = toDouble(padding["topDp"]) ?? 0
        let left = toDouble(padding["leftDp"]) ?? 0
        let bottom = toDouble(padding["bottomDp"]) ?? 0
        let right = toDouble(padding["rightDp"]) ?? 0
        lines.append("\(baseIndent).padding(EdgeInsets(top: \(top), leading: \(left), bottom: \(bottom), trailing: \(right)))")
    }

    let tokenRef = toString(props["tokenRef"])
    if tokenRef.hasPrefix("#"), tokenRef.count == 7 {
        let hex = sanitizeSwiftString(tokenRef)
        lines.append("\(baseIndent).background(Color(hex: \"\(hex)\"))")
    }

    if offsetX != 0 || offsetY != 0 {
        lines.append("\(baseIndent).offset(x: \(offsetX), y: \(offsetY))")
    }

    let testTag = sanitizeSwiftString(toString(props["testTag"]))
    if !testTag.isEmpty {
        lines.append("\(baseIndent).accessibilityIdentifier(\"\(testTag)\")")
    }
    let contentDescription = sanitizeSwiftString(toString(props["contentDescription"]))
    if !contentDescription.isEmpty {
        lines.append("\(baseIndent).accessibilityLabel(\"\(contentDescription)\")")
    }

    if lines.isEmpty {
        return ""
    }
    return "\n" + lines.joined(separator: "\n")
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

func emitNode(_ node: [String: Any], indent: Int) -> String {
    let space = String(repeating: "    ", count: indent)
    let nodeKey = toString(node["node"])
    let props = toDictionary(node["props"])
    let children = toArray(node["children"])
    let childCode = children.map { emitNode($0, indent: indent + 1) }.joined(separator: "\n")
    let spacing = toInt(props["spacingDp"]) ?? 0
    let text = textLiteral(node: node, props: props)
    let nodeNameFallback = toString(node["name"]).isEmpty ? "placeholder" : toString(node["name"])
    let resourceCandidate = toString(props["resourceName"]).isEmpty ? nodeNameFallback : toString(props["resourceName"])
    let resourceName = sanitizeSwiftString(resourceCandidate)
    let checked = toString(node["state"]) == "checked" ? "true" : "false"
    let layoutKind = resolvedLayout(nodeKey: nodeKey, props: props)

    if nodeKey == "layout/column" || nodeKey == "layout/stack" || (nodeKey == "layout/constraint" && layoutKind == "column") || (nodeKey == "layout/flow" && layoutKind == "column") {
        return """
\(space)VStack(alignment: .leading, spacing: \(spacing)) {
\(childCode)
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    }
    if nodeKey == "layout/row" || (nodeKey == "layout/constraint" && layoutKind == "row") || (nodeKey == "layout/flow" && layoutKind == "row") {
        return """
\(space)HStack(alignment: .center, spacing: \(spacing)) {
\(childCode)
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    }
    if nodeKey == "layout/grid" || layoutKind == "grid" {
        return """
\(space)LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: \(spacing)) {
\(childCode)
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    }
    if nodeKey == "layout/box" || nodeKey == "layout/constraint" || nodeKey == "layout/flow" {
        return """
\(space)ZStack {
\(childCode)
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    }

    switch nodeKey {
    case "screen/page":
        return """
\(space)ScrollView {
\(space)    VStack(alignment: .leading, spacing: \(spacing)) {
\(childCode)
\(space)    }
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    case "screen/bottomSheet":
        return """
\(space)VStack(alignment: .leading, spacing: \(spacing)) {
\(childCode)
\(space)}
\(space).padding(16)
\(space).background(.ultraThinMaterial)
\(space).clipShape(RoundedRectangle(cornerRadius: 16))\(emitModifierChain(props: props, baseIndent: space))
"""
    case "screen/dialog":
        return """
\(space)VStack(alignment: .leading, spacing: \(spacing)) {
\(childCode)
\(space)}
\(space).padding(20)
\(space).background(Color.white)
\(space).clipShape(RoundedRectangle(cornerRadius: 12))
\(space).shadow(radius: 8)\(emitModifierChain(props: props, baseIndent: space))
"""
    case "content/text":
        return "\(space)Text(\"\(text)\")\(emitModifierChain(props: props, baseIndent: space))"
    case "content/icon", "content/image", "content/illustration":
        return "\(space)Image(\"\(resourceName)\")\(emitModifierChain(props: props, baseIndent: space))"
    case "content/video", "content/lottie":
        return """
\(space)ZStack {
\(space)    RoundedRectangle(cornerRadius: 8).fill(Color.gray.opacity(0.2))
\(space)    Text("Media: \(text)")
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    case "component/list":
        return """
\(space)ScrollView {
\(space)    LazyVStack(alignment: .leading, spacing: \(spacing)) {
\(childCode)
\(space)    }
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    case "component/listItem", "component/card":
        return """
\(space)VStack(alignment: .leading, spacing: \(spacing)) {
\(childCode)
\(space)}
\(space).padding(12)
\(space).background(Color.gray.opacity(0.08))
\(space).clipShape(RoundedRectangle(cornerRadius: 10))\(emitModifierChain(props: props, baseIndent: space))
"""
    case "component/button", "component/fab", "component/iconButton", "component/chip", "component/toggleChip", "component/segmentedControl":
        return """
\(space)Button(action: {}) {
\(space)    if !\(resourceName == "placeholder" ? "true" : "false") {
\(space)        Image("\(resourceName)")
\(space)    } else {
\(space)        Text("\(text)")
\(space)    }
\(space)}
\(space).buttonStyle(.borderedProminent)\(emitModifierChain(props: props, baseIndent: space))
"""
    case "component/textField", "component/searchField":
        return "\(space)TextField(\"\(text)\", text: .constant(\"\"))\(emitModifierChain(props: props, baseIndent: space))"
    case "component/passwordField":
        return "\(space)SecureField(\"\(text)\", text: .constant(\"\"))\(emitModifierChain(props: props, baseIndent: space))"
    case "component/checkbox", "component/switch", "component/radio":
        return """
\(space)Toggle(isOn: .constant(\(checked))) {
\(space)    Text("\(text)")
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    case "component/slider", "component/rangeSlider":
        return "\(space)Slider(value: .constant(0.5), in: 0...1)\(emitModifierChain(props: props, baseIndent: space))"
    case "component/stepper":
        return "\(space)Stepper(\"\(text)\", value: .constant(0), in: 0...100)\(emitModifierChain(props: props, baseIndent: space))"
    case "component/datePicker":
        return "\(space)DatePicker(\"\(text)\", selection: .constant(Date()), displayedComponents: .date)\(emitModifierChain(props: props, baseIndent: space))"
    case "component/timePicker":
        return "\(space)DatePicker(\"\(text)\", selection: .constant(Date()), displayedComponents: .hourAndMinute)\(emitModifierChain(props: props, baseIndent: space))"
    case "component/dropdown":
        return """
\(space)Picker("\(text)", selection: .constant("Option 1")) {
\(space)    Text("Option 1").tag("Option 1")
\(space)    Text("Option 2").tag("Option 2")
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    case "component/table":
        return """
\(space)VStack(alignment: .leading, spacing: \(spacing)) {
\(childCode)
\(space)}
\(space).overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.gray.opacity(0.3), lineWidth: 1))\(emitModifierChain(props: props, baseIndent: space))
"""
    case "component/badge":
        return """
\(space)Text("\(text)")
\(space).font(.caption)
\(space).padding(.horizontal, 8)
\(space).padding(.vertical, 4)
\(space).background(Color.gray.opacity(0.2))
\(space).clipShape(Capsule())\(emitModifierChain(props: props, baseIndent: space))
"""
    case "component/avatar":
        return """
\(space)Circle()
\(space)    .fill(Color.gray.opacity(0.3))
\(space)    .overlay(Text("\(text.prefix(2))"))\(emitModifierChain(props: props, baseIndent: space))
"""
    case "component/progressLinear":
        return "\(space)ProgressView(value: 0.5)\(emitModifierChain(props: props, baseIndent: space))"
    case "component/progressCircular", "feedback/loading":
        return "\(space)ProgressView()\(emitModifierChain(props: props, baseIndent: space))"
    case "component/divider":
        return "\(space)Divider()\(emitModifierChain(props: props, baseIndent: space))"
    case "component/snackbar", "component/toast", "component/tooltip", "component/banner", "feedback/error", "feedback/empty", "feedback/success", "feedback/offline":
        return """
\(space)Text("\(text)")
\(space).padding(10)
\(space).background(Color.gray.opacity(0.15))
\(space).clipShape(RoundedRectangle(cornerRadius: 8))\(emitModifierChain(props: props, baseIndent: space))
"""
    case "raw/frame":
        return """
\(space)Group {
\(childCode)
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    default:
        return """
\(space)VStack(alignment: .leading, spacing: \(spacing)) {
\(space)    Text("Unsupported node: \(sanitizeSwiftString(nodeKey))")
\(childCode)
\(space)}\(emitModifierChain(props: props, baseIndent: space))
"""
    }
}

func buildScreenFile(moduleName: String, screenName: String, node: [String: Any]) -> String {
    let body = emitNode(node, indent: 2)
    return """
import SwiftUI

// DO NOT EDIT: generated by pipeline
public struct \(screenName)Screen: View {
    public init() {}

    public var body: some View {
\(body)
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
}

func buildPreviewFile(moduleName: String, screenName: String) -> String {
    return """
import SwiftUI

// DO NOT EDIT: generated by pipeline
#Preview {
    \(screenName)Screen()
}
"""
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
