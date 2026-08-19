import AppKit
import Foundation
import Vision

struct ScanResult: Codable {
    let path: String
    let texts: [String]
    let qrCount: Int
    let error: String?
}

func scan(path: String) -> ScanResult {
    guard let image = NSImage(contentsOfFile: path) else {
        return ScanResult(path: path, texts: [], qrCount: 0, error: "image-open-failed")
    }
    var proposed = NSRect(origin: .zero, size: image.size)
    guard let cgImage = image.cgImage(forProposedRect: &proposed, context: nil, hints: nil) else {
        return ScanResult(path: path, texts: [], qrCount: 0, error: "cgimage-conversion-failed")
    }

    let textRequest = VNRecognizeTextRequest()
    textRequest.recognitionLevel = .accurate
    textRequest.recognitionLanguages = ["zh-Hans", "en-US"]
    textRequest.usesLanguageCorrection = false

    let barcodeRequest = VNDetectBarcodesRequest()
    barcodeRequest.symbologies = [.qr]

    do {
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([textRequest, barcodeRequest])
        let texts = (textRequest.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let qrCount = barcodeRequest.results?.count ?? 0
        return ScanResult(path: path, texts: texts, qrCount: qrCount, error: nil)
    } catch {
        return ScanResult(path: path, texts: [], qrCount: 0, error: "vision-request-failed")
    }
}

let results = CommandLine.arguments.dropFirst().map { scan(path: $0) }
let encoder = JSONEncoder()
encoder.outputFormatting = [.withoutEscapingSlashes]
if let data = try? encoder.encode(results), let output = String(data: data, encoding: .utf8) {
    print(output)
} else {
    print("[]")
}
