# 📸 Remove Background Skill

A powerful Agentic skill that removes white and light backgrounds from images to produce true transparent PNGs with proper alpha channels. Works beautifully for logos, icons, product photos, and images with fake checkerboard "transparency" patterns.

## Example: NexaFlow Logo

Here is a demonstration of the skill in action on a generated dummy logo:

### Before (White Background)
<img src="examples/nexaflow_original.png" width="400" alt="Original Logo on White Background" />

### After (Transparent Background)
<img src="examples/nexaflow_transparent.png" width="400" alt="Transparent Logo" />

*(Note: The transparent PNG will blend seamlessly into whatever background color it is placed on.)*

---

## Technical Details

This skill is designed for use by AI agents. The detailed agent guidelines, prerequisites, processing modes (e.g., `white`, `light`, `ai`), and algorithm strategies are fully documented in the [`SKILL.md`](SKILL.md) file.

**Features include:**
- Smooth anti-aliasing edge detection
- Color recovery at semi-transparent borders to prevent white halos
- Support for multiple processing layers (color-distance rendering and U2Net segmentation)
- Auto-cropping of transparent borders
