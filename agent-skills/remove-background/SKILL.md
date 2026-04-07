---
name: remove-background
description: Remove white/light backgrounds from images to create proper transparent PNGs. Handles logos, icons, product photos, and multi-object images. Invoke when user asks to make an image transparent, remove background, or convert to "real PNG".
---

# Remove Background Skill

Convert any image to a proper transparent PNG by removing white/light backgrounds. Works with logos, icons, product photos, screenshots, and images containing multiple objects.

## Trigger Conditions

This skill activates when:
- User asks to "remove background" from an image
- User asks to "make transparent" or "convert to real PNG"
- User wants white/light backgrounds removed from logos or icons
- User references fake transparency (checkerboard patterns) that need to be replaced with real alpha

## Prerequisites

The skill script requires Python 3 with these packages:
- `Pillow` (PIL) — image processing
- `numpy` — array operations
- `scipy` — for advanced checkerboard detection (optional, graceful fallback)

### Setup (one-time)

Ensure the workspace-level Python venv exists and has dependencies:

```bash
# From the workspace root
python3 -m venv venv 2>/dev/null
source venv/bin/activate
pip install Pillow numpy scipy --quiet
```

## Usage

### Basic Command

```bash
source venv/bin/activate
python <SKILL_DIR>/scripts/remove_bg.py \
  --input <input_image_path> \
  --output <output_directory> \
  [options]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--input`, `-i` | Input image path (any format: PNG, JPG, WEBP, etc.) | **required** |
| `--output`, `-o` | Output directory for transparent PNGs | Same dir as input |
| `--name`, `-n` | Output filename (without .png extension) | Input filename |
| `--threshold-low` | White distance threshold — below = transparent | `15` |
| `--threshold-high` | White distance threshold — above = opaque | `42` |
| `--white-tolerance` | RGB distance from pure white to treat as "white" | `15` |
| `--remove-checkerboard` | Also remove fake checkerboard transparency patterns | `true` |
| `--mode` | Processing mode: `white`, `light`, `ai` | `white` |
| `--preview` | Generate an HTML preview file to verify transparency | `false` |

### Processing Modes

- **`white`** (default): Remove white and near-white pixels. Best for logos, icons, and images on solid white backgrounds. Fast and reliable.
- **`light`**: Remove light-colored backgrounds (not just white). More aggressive — works for off-white, light gray, or slightly colored backgrounds.
- **`ai`**: Use the `rembg` library (U2Net AI model) for subject-based segmentation. Best for photos where the subject needs to be isolated from any background. Note: may remove text — not recommended for logos.

### Examples

#### Single image, basic white removal:
```bash
python remove_bg.py -i logo.jpg -o ./output/
```

#### Custom filename:
```bash
python remove_bg.py -i screenshot.webp -o ./output/ -n company-logo
```

#### With preview verification:
```bash
python remove_bg.py -i logo.png -o ./output/ --preview
# Opens output/preview.html showing the logo on multiple colored backgrounds
```

#### More aggressive removal for off-white backgrounds:
```bash
python remove_bg.py -i photo.jpg -o ./output/ --mode light --threshold-high 60
```

#### AI-powered removal (requires rembg + onnxruntime):
```bash
pip install rembg onnxruntime --quiet
python remove_bg.py -i product_photo.jpg -o ./output/ --mode ai
```

## How It Works

### White Removal Algorithm

1. **Color Distance**: Calculate Euclidean distance from each pixel to pure white `(255,255,255)` in RGB space
2. **Alpha Assignment**:
   - Distance < `threshold-low` → fully transparent (α=0)
   - Distance > `threshold-high` → fully opaque (α=255)
   - In between → gradual alpha for smooth anti-aliased edges
3. **Checkerboard Detection**: Identifies fake transparency checkerboard patterns (alternating white and gray squares) using:
   - Neutral gray detection (R≈G≈B, brightness 170-235)
   - Local variance analysis via scipy (detects alternating pattern)
4. **Edge Color Recovery**: For semi-transparent edge pixels, reverse the white-compositing formula to recover original colors: `C = (V - W*(1-α)) / α`
5. **Post-processing**: Final cleanup pass removes any remaining isolated neutral gray artifacts

### Key Design Decisions
- Uses distance-based alpha (not binary threshold) for **smooth anti-aliased edges**
- Recovers original colors at semi-transparent boundaries to prevent **white halos**
- Handles checkerboard patterns that some tools generate as "fake transparency"
- Does NOT remove dark grays or colored pixels — safe for logos with text

## Verification

After generating transparent PNGs, verify them by:

1. **Use `--preview` flag** to generate an HTML file showing the logo on 5 colored backgrounds
2. **View the PNG directly** — in the agent, use `view_file` on the output PNG to visually inspect

### What to check:
- ✅ No white boxes or halos around the logo
- ✅ All text is preserved and readable
- ✅ Anti-aliased edges are smooth (no jagged cutoffs)
- ✅ No checkerboard artifacts remaining

## Troubleshooting

| Issue | Fix |
|-------|-----|
| White halo around edges | Lower `--threshold-high` (try 35) |
| Logo content being removed | Raise `--threshold-low` (try 20) and `--threshold-high` (try 50) |
| Gray text disappearing | The post-processing may be too aggressive — check if text is neutral gray |
| Checkerboard still visible | Ensure `--remove-checkerboard` is on, or try `--mode light` |
| AI mode removes text | Use `--mode white` instead — AI mode isn't designed for logos |
