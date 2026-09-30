// Position-aware PDF text extraction (macOS PDFKit + Vision), for putting multi-column pages back in reading order.
// Usage: layout_extract <list-file> <out-dir>
//   <list-file>: one "<absolute pdf path>\t<output name>" per line
//   writes <out-dir>/<output name>.json:
//   {"pages":[{"w":612,"h":792,"ocr":false,"segs":[[text, x0, top, x1, bottom, fontSize, bold], ...]}]}
// A "seg" is a run of characters on one baseline with no large horizontal gap; coordinates are in points
// with the origin at the top-left of the page. Ordering into columns happens later, in reextract.py.
import Foundation
import PDFKit
import AppKit
import Vision

let args = CommandLine.arguments
let jobs = try! String(contentsOfFile: args[1], encoding: .utf8).split(separator: "\n").map(String.init)
let outDir = URL(fileURLWithPath: args[2])

func segments(_ page: PDFPage) -> [[Any]] {
    // PDFKit's line selections keep each line's text and position together (per-character bounds can drift
    // out of step with the text on some files).
    let box = page.bounds(for: .mediaBox)
    guard let all = page.selection(for: box) else { return [] }
    var segs: [[Any]] = []
    for line in all.selectionsByLine() {
        guard let raw = line.string else { continue }
        let t = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { continue }
        let r = line.bounds(for: page)
        var size: CGFloat = 0, bold = true, any = false
        if let a = line.attributedString {
            a.enumerateAttribute(.font, in: NSRange(location: 0, length: a.length), options: []) { v, rng, _ in
                guard let f = v as? NSFont else { return }
                let chunk = (a.string as NSString).substring(with: rng).trimmingCharacters(in: .whitespacesAndNewlines)
                if chunk.isEmpty { return }
                any = true
                size = max(size, f.pointSize)
                let n = f.fontName.lowercased()
                if !(n.contains("bold") || n.contains("black") || n.contains("heavy")) { bold = false }
            }
        }
        if !any { bold = false; size = r.height * 0.8 }
        segs.append([t, Double(r.minX), Double(box.maxY - r.maxY), Double(r.maxX), Double(box.maxY - r.minY), Double(size), bold])
    }
    return segs
}

// Pages with no text layer: Vision OCR, keeping each line's box.
func ocrSegments(_ page: PDFPage) -> [[Any]] {
    let bnd = page.bounds(for: .mediaBox)
    let scale: CGFloat = 2.5
    let w = Int(bnd.width * scale), h = Int(bnd.height * scale)
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return [] }
    ctx.setFillColor(NSColor.white.cgColor); ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    guard let img = ctx.makeImage() else { return [] }
    let req = VNRecognizeTextRequest(); req.recognitionLevel = .accurate; req.usesLanguageCorrection = true
    try? VNImageRequestHandler(cgImage: img, orientation: .up).perform([req])
    return (req.results ?? []).compactMap { o in
        guard let s = o.topCandidates(1).first?.string else { return nil }
        let bb = o.boundingBox   // normalized, origin bottom-left
        let x0 = bb.minX * bnd.width, x1 = bb.maxX * bnd.width
        let top = (1 - bb.maxY) * bnd.height, bottom = (1 - bb.minY) * bnd.height
        return [s, Double(x0), Double(top), Double(x1), Double(bottom), Double((bottom - top) * 0.8), false]
    }
}

for job in jobs {
    let parts = job.components(separatedBy: "\t")
    guard parts.count == 2 else { continue }
    autoreleasepool {
        guard let doc = PDFDocument(url: URL(fileURLWithPath: parts[0])) else { print("FAILED \(parts[1])"); return }
        var pages: [[String: Any]] = []
        for pi in 0..<doc.pageCount {
            guard let page = doc.page(at: pi) else { continue }
            let b = page.bounds(for: .mediaBox)
            var segs = segments(page)
            var ocr = false
            if segs.map({ ($0[0] as! String).count }).reduce(0, +) < 20 { segs = ocrSegments(page); ocr = true }
            pages.append(["w": Double(b.width), "h": Double(b.height), "ocr": ocr, "segs": segs])
        }
        if let d = try? JSONSerialization.data(withJSONObject: ["pages": pages]) {
            try? d.write(to: outDir.appendingPathComponent(parts[1] + ".json"))
        }
        print("ok \(parts[1])")
    }
}
