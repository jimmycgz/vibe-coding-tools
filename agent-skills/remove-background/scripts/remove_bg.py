#!/usr/bin/env python3
"""
remove_bg.py — Remove white/light backgrounds from images to create transparent PNGs.

Handles:
- Logos, icons, and graphics on white backgrounds
- Fake checkerboard "transparency" patterns
- Anti-aliased edges (smooth alpha transitions)
- Multiple objects in a single image
- Various input formats (PNG, JPG, WEBP, BMP, TIFF, etc.)

Usage:
    python remove_bg.py --input logo.jpg --output ./output/
    python remove_bg.py -i photo.webp -o ./out/ --mode light --preview
    python remove_bg.py -i product.jpg -o ./out/ --mode ai
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

# Optional dependencies
try:
    from scipy.ndimage import uniform_filter
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from rembg import remove as rembg_remove
    HAS_REMBG = True
except ImportError:
    HAS_REMBG = False


def detect_checkerboard(arr_rgb: np.ndarray) -> np.ndarray:
    """
    Detect fake transparency checkerboard patterns.

    The classic checkerboard uses alternating squares of:
    - White: ~(255, 255, 255)
    - Light gray: ~(204, 204, 204) or similar

    Returns a boolean mask where True = checkerboard pixel to remove.
    """
    r = arr_rgb[:, :, 0].astype(float)
    g = arr_rgb[:, :, 1].astype(float)
    b = arr_rgb[:, :, 2].astype(float)

    # Pixel is neutral (R ≈ G ≈ B)
    is_neutral = (np.abs(r - g) < 12) & (np.abs(g - b) < 12) & (np.abs(r - b) < 12)

    brightness = (r + g + b) / 3.0

    # Gray range typical for checkerboard (170–235)
    is_checker_gray = is_neutral & (brightness > 170) & (brightness < 235)

    if HAS_SCIPY:
        # Use local variance to detect the alternating pattern
        local_mean = uniform_filter(brightness, size=10)
        local_var = uniform_filter((brightness - local_mean) ** 2, size=10)
        # Checkerboard has moderate variance from alternating ~255 and ~204
        high_var_neutral = (local_var > 80) & is_neutral & (brightness > 160)
        checkerboard = is_checker_gray | high_var_neutral
    else:
        # Fallback: just use the gray range detection
        checkerboard = is_checker_gray

    return checkerboard


def remove_white_background(
    pil_img: Image.Image,
    threshold_low: float = 15.0,
    threshold_high: float = 42.0,
    remove_checker: bool = True,
) -> Image.Image:
    """
    Remove white/near-white background from a PIL image.

    Uses distance-based alpha with:
    - Smooth anti-aliased edge handling
    - Optional checkerboard pattern removal
    - Edge color recovery to prevent white halos

    Args:
        pil_img: Input PIL image (any mode, will be converted to RGBA)
        threshold_low: Distance from white below which pixels are fully transparent
        threshold_high: Distance from white above which pixels are fully opaque
        remove_checker: Whether to also detect and remove checkerboard patterns

    Returns:
        PIL Image in RGBA mode with transparent background
    """
    img = pil_img.convert("RGBA")
    arr = np.array(img).astype(np.float64)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    # Euclidean distance from pure white in RGB space
    dist = np.sqrt((255.0 - r) ** 2 + (255.0 - g) ** 2 + (255.0 - b) ** 2)

    # Build alpha channel
    alpha = np.zeros_like(r)
    alpha[dist >= threshold_high] = 255.0
    transition = (dist >= threshold_low) & (dist < threshold_high)
    alpha[transition] = 255.0 * (dist[transition] - threshold_low) / (
        threshold_high - threshold_low
    )

    # Checkerboard removal
    if remove_checker:
        checker_mask = detect_checkerboard(arr[:, :, :3])
        alpha[checker_mask] = 0.0

    # Color recovery for semi-transparent edge pixels
    # When a colored pixel was composited on white, the visible color V =
    #   C * a + 255 * (1 - a), so original color C = (V - 255*(1-a)) / a
    semi = (alpha > 5) & (alpha < 250)
    if np.any(semi):
        a_norm = np.maximum(alpha[semi] / 255.0, 0.1)
        for ch in range(3):
            channel = arr[:, :, ch]
            recovered = (channel[semi] - 255.0 * (1.0 - a_norm)) / a_norm
            channel[semi] = np.clip(recovered, 0, 255)
            arr[:, :, ch] = channel

    arr[:, :, 3] = np.clip(alpha, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def remove_light_background(
    pil_img: Image.Image,
    threshold_low: float = 20.0,
    threshold_high: float = 60.0,
    remove_checker: bool = True,
) -> Image.Image:
    """
    Remove light-colored backgrounds (not just white).

    More aggressive than white removal — catches off-white, light gray,
    and slightly colored backgrounds.
    """
    img = pil_img.convert("RGBA")
    arr = np.array(img).astype(np.float64)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    # Use brightness + saturation to detect "light" pixels
    brightness = (r + g + b) / 3.0
    max_ch = np.maximum(np.maximum(r, g), b)
    min_ch = np.minimum(np.minimum(r, g), b)
    saturation = np.where(max_ch > 0, (max_ch - min_ch) / max_ch, 0)

    # Light background: high brightness, low saturation
    # Distance metric combines brightness and saturation
    light_dist = np.sqrt((255.0 - brightness) ** 2 + (saturation * 200) ** 2)

    alpha = np.zeros_like(r)
    alpha[light_dist >= threshold_high] = 255.0
    transition = (light_dist >= threshold_low) & (light_dist < threshold_high)
    alpha[transition] = 255.0 * (light_dist[transition] - threshold_low) / (
        threshold_high - threshold_low
    )

    if remove_checker:
        checker_mask = detect_checkerboard(arr[:, :, :3])
        alpha[checker_mask] = 0.0

    semi = (alpha > 5) & (alpha < 250)
    if np.any(semi):
        a_norm = np.maximum(alpha[semi] / 255.0, 0.1)
        for ch in range(3):
            channel = arr[:, :, ch]
            recovered = (channel[semi] - 255.0 * (1.0 - a_norm)) / a_norm
            channel[semi] = np.clip(recovered, 0, 255)
            arr[:, :, ch] = channel

    arr[:, :, 3] = np.clip(alpha, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def remove_background_ai(pil_img: Image.Image) -> Image.Image:
    """
    Use rembg (U2Net AI model) for subject-based segmentation.

    Best for photos where the subject needs to be isolated from any background.
    Note: May remove text — not recommended for logos.

    Requires: pip install rembg onnxruntime
    """
    if not HAS_REMBG:
        print("ERROR: rembg is not installed. Install with:")
        print("  pip install rembg onnxruntime")
        sys.exit(1)

    img = pil_img.convert("RGBA")
    return rembg_remove(img)


def auto_crop(pil_img: Image.Image, margin: int = 2) -> Image.Image:
    """
    Auto-crop transparent borders, keeping a small margin.
    """
    arr = np.array(pil_img)
    if arr.shape[2] < 4:
        return pil_img

    alpha = arr[:, :, 3]
    has_content_rows = np.any(alpha > 10, axis=1)
    has_content_cols = np.any(alpha > 10, axis=0)

    if not np.any(has_content_rows) or not np.any(has_content_cols):
        return pil_img

    top = max(0, np.argmax(has_content_rows) - margin)
    bottom = min(arr.shape[0], len(has_content_rows) - np.argmax(has_content_rows[::-1]) + margin)
    left = max(0, np.argmax(has_content_cols) - margin)
    right = min(arr.shape[1], len(has_content_cols) - np.argmax(has_content_cols[::-1]) + margin)

    return pil_img.crop((left, top, right, bottom))


def generate_preview_html(output_dir: str, image_filenames: list) -> str:
    """
    Generate an HTML preview file that displays images on multiple colored backgrounds
    to visually verify transparency.
    """
    cards = ""
    for fname in image_filenames:
        name = Path(fname).stem.replace("_", " ").replace("-", " ").title()
        cards += f"""
    <div class="logo-section">
        <h2>{name}</h2>
        <div class="row">
            <div class="box bg-dark"><img src="{fname}"><span>Dark</span></div>
            <div class="box bg-blue"><img src="{fname}"><span>Blue</span></div>
            <div class="box bg-green"><img src="{fname}"><span>Green</span></div>
            <div class="box bg-yellow"><img src="{fname}"><span>Yellow</span></div>
            <div class="box bg-red"><img src="{fname}"><span>Red</span></div>
            <div class="box bg-checker"><img src="{fname}"><span>Checker</span></div>
        </div>
    </div>
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transparency Preview</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f0f2f5; padding: 24px; color: #1a1a2e;
        }}
        h1 {{ margin-bottom: 8px; font-size: 24px; }}
        .subtitle {{ color: #666; margin-bottom: 24px; font-size: 14px; }}
        .logo-section {{ margin-bottom: 32px; }}
        .logo-section h2 {{ font-size: 18px; margin-bottom: 12px; }}
        .row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
        .box {{
            padding: 16px; border-radius: 10px; text-align: center;
            min-width: 120px; display: flex; flex-direction: column;
            align-items: center; gap: 8px;
        }}
        .box img {{ max-width: 120px; max-height: 120px; object-fit: contain; }}
        .box span {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
        .bg-dark {{ background: #1a1a2e; color: #aaa; }}
        .bg-blue {{ background: #4a90d9; color: #fff; }}
        .bg-green {{ background: #2d6a4f; color: #ccc; }}
        .bg-yellow {{ background: #f4d35e; color: #555; }}
        .bg-red {{ background: #c1121f; color: #fcc; }}
        .bg-checker {{
            background: repeating-conic-gradient(#ddd 0% 25%, #fff 0% 50%) 50% / 16px 16px;
            color: #666;
        }}
    </style>
</head>
<body>
    <h1>🔍 Transparency Preview</h1>
    <p class="subtitle">Each image is shown on 6 backgrounds. If you see a white box or checkerboard, the background wasn't fully removed.</p>
    {cards}
</body>
</html>"""

    preview_path = os.path.join(output_dir, "preview.html")
    with open(preview_path, "w") as f:
        f.write(html)
    return preview_path


def process_image(
    input_path: str,
    output_dir: str,
    output_name: Optional[str] = None,
    mode: str = "white",
    threshold_low: float = 15.0,
    threshold_high: float = 42.0,
    remove_checker: bool = True,
    auto_crop_result: bool = True,
) -> str:
    """
    Process a single image: remove background and save as transparent PNG.

    Returns the output file path.
    """
    # Load image
    img = Image.open(input_path)
    print(f"Input: {input_path} ({img.size[0]}x{img.size[1]}, {img.mode})")

    # Determine output filename
    if output_name is None:
        output_name = Path(input_path).stem
    output_path = os.path.join(output_dir, f"{output_name}.png")

    # Remove background based on mode
    if mode == "white":
        result = remove_white_background(
            img,
            threshold_low=threshold_low,
            threshold_high=threshold_high,
            remove_checker=remove_checker,
        )
    elif mode == "light":
        result = remove_light_background(
            img,
            threshold_low=threshold_low,
            threshold_high=threshold_high,
            remove_checker=remove_checker,
        )
    elif mode == "ai":
        result = remove_background_ai(img)
    else:
        print(f"ERROR: Unknown mode '{mode}'. Use 'white', 'light', or 'ai'.")
        sys.exit(1)

    # Auto-crop transparent borders
    if auto_crop_result:
        result = auto_crop(result)

    # Save
    result.save(output_path, "PNG")
    file_size = os.path.getsize(output_path)

    # Stats
    arr = np.array(result)
    total = arr.shape[0] * arr.shape[1]
    transparent = int(np.sum(arr[:, :, 3] == 0))
    opaque = int(np.sum(arr[:, :, 3] == 255))
    semi = total - transparent - opaque
    transparency_pct = (transparent / total) * 100

    print(f"Output: {output_path}")
    print(f"  Size: {result.size[0]}x{result.size[1]}, {file_size:,} bytes")
    print(f"  Pixels: {total:,} total | {transparent:,} transparent ({transparency_pct:.1f}%) | {opaque:,} opaque | {semi:,} semi-transparent")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Remove white/light backgrounds from images to create transparent PNGs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -i logo.jpg -o ./output/
  %(prog)s -i screenshot.webp -o ./output/ -n company-logo --preview
  %(prog)s -i photo.jpg -o ./output/ --mode light --threshold-high 60
  %(prog)s -i product.jpg -o ./output/ --mode ai
        """,
    )
    parser.add_argument("-i", "--input", required=True, help="Input image path")
    parser.add_argument("-o", "--output", default=None, help="Output directory (default: same as input)")
    parser.add_argument("-n", "--name", default=None, help="Output filename without .png extension")
    parser.add_argument("--mode", default="white", choices=["white", "light", "ai"],
                        help="Processing mode (default: white)")
    parser.add_argument("--threshold-low", type=float, default=15.0,
                        help="White distance threshold — below = transparent (default: 15)")
    parser.add_argument("--threshold-high", type=float, default=42.0,
                        help="White distance threshold — above = opaque (default: 42)")
    parser.add_argument("--remove-checkerboard", action="store_true", default=True,
                        help="Remove fake checkerboard patterns (default: true)")
    parser.add_argument("--no-checkerboard", dest="remove_checkerboard", action="store_false",
                        help="Don't remove checkerboard patterns")
    parser.add_argument("--no-autocrop", action="store_true", default=False,
                        help="Don't auto-crop transparent borders")
    parser.add_argument("--preview", action="store_true", default=False,
                        help="Generate HTML preview for verification")

    args = parser.parse_args()

    # Validate input
    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    # Set output directory
    if args.output is None:
        args.output = str(Path(args.input).parent)

    os.makedirs(args.output, exist_ok=True)

    # Process
    output_path = process_image(
        input_path=args.input,
        output_dir=args.output,
        output_name=args.name,
        mode=args.mode,
        threshold_low=args.threshold_low,
        threshold_high=args.threshold_high,
        remove_checker=args.remove_checkerboard,
        auto_crop_result=not args.no_autocrop,
    )

    # Generate preview
    if args.preview:
        output_filename = os.path.basename(output_path)
        preview_path = generate_preview_html(args.output, [output_filename])
        print(f"\n🔍 Preview: {preview_path}")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
