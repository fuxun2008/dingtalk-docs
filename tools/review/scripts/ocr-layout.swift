import AppKit
import Foundation
import Vision

struct Box: Codable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct TextObservation: Codable {
    let text: String
    let confidence: Float
    let box: Box
}

struct LayoutResult: Codable {
    let path: String
    let texts: [TextObservation]
    let qrCodes: [Box]
    let error: String?
}

func box(_ rect: CGRect) -> Box {
    Box(
        x: rect.origin.x,
        y: rect.origin.y,
        width: rect.size.width,
        height: rect.size.height
    )
}

func scan(path: String) -> LayoutResult {
    guard let image = NSImage(contentsOfFile: path) else {
        return LayoutResult(path: path, texts: [], qrCodes: [], error: "image-open-failed")
    }
    var proposed = NSRect(origin: .zero, size: image.size)
    guard let cgImage = image.cgImage(forProposedRect: &proposed, context: nil, hints: nil) else {
        return LayoutResult(path: path, texts: [], qrCodes: [], error: "cgimage-conversion-failed")
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
        let texts = (textRequest.results ?? []).compactMap { observation -> TextObservation? in
            guard let candidate = observation.topCandidates(1).first else { return nil }
            return TextObservation(
                text: candidate.string,
                confidence: candidate.confidence,
                box: box(observation.boundingBox)
            )
        }
        let qrCodes = (barcodeRequest.results ?? []).map { box($0.boundingBox) }
        return LayoutResult(path: path, texts: texts, qrCodes: qrCodes, error: nil)
    } catch {
        return LayoutResult(path: path, texts: [], qrCodes: [], error: "vision-request-failed")
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
