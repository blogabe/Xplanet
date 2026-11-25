// Read a pristine local night map and composite the bounded OVATION PNG.
import Foundation
import CoreGraphics
import ImageIO

func load(_ path: String) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
          let w = props[kCGImagePropertyPixelWidth] as? Int,
          let h = props[kCGImagePropertyPixelHeight] as? Int,
          w > 0, h > 0, w <= 100_000_000 / h else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}

let args = CommandLine.arguments
guard args.count == 4, let base = load(args[1]), let mask = load(args[2]),
      let ctx = CGContext(data: nil, width: base.width, height: base.height,
                          bitsPerComponent: 8, bytesPerRow: 0,
                          space: CGColorSpace(name: CGColorSpace.sRGB)!,
                          bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { exit(1) }
let bounds = CGRect(x: 0, y: 0, width: base.width, height: base.height)
ctx.interpolationQuality = .high
ctx.draw(base, in: bounds)
ctx.draw(mask, in: bounds)
guard let image = ctx.makeImage(),
      let dst = CGImageDestinationCreateWithURL(URL(fileURLWithPath: args[3]) as CFURL,
                                                "public.png" as CFString, 1, nil) else { exit(2) }
CGImageDestinationAddImage(dst, image, nil)
guard CGImageDestinationFinalize(dst), let check = load(args[3]),
      check.width == base.width, check.height == base.height else { exit(3) }
