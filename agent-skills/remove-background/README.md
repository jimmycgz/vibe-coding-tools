# 📸 Remove Background Skill

A powerful Agentic skill that removes white and light backgrounds from images to produce true transparent PNGs with proper alpha channels. Works beautifully for logos, icons, product photos, and images with fake checkerboard "transparency" patterns.

## Example: NexaFlow Logo

Here is a demonstration of the skill in action. Because standard GitHub Markdown doesn't show transparency well natively, this preview composites the result over a checkerboard background to prove the true alpha channel processing!

### Before (White Background) & After (True Transparent Alpha)
<div align="center">
  <img src="examples/nexaflow_original.png" width="300" alt="Original" />
  <img src="examples/checker_preview.png" width="300" alt="Transparent on Checkerboard" />
</div>

---

## Technical Details

This skill is designed for use by AI agents. The detailed agent guidelines, prerequisites, processing modes (e.g., `white`, `light`, `ai`), and algorithm strategies are fully documented in the [`SKILL.md`](SKILL.md) file.

### Why Standard AI Models Fail
Most AI background removal tools (like *rembg*, remove.bg, or Apple subject cutout) are trained on **photographs** to separate a "foreground subject" from a "background." 
1. **They destroy text:** When an AI sees a logo, it usually identifies the "icon" as the foreground subject and assumes the brand text is just background noise. 
2. **They misinterpret fake transparency:** Standard tools don't know what to do with screenshots containing that fake white/grey checkerboard pattern. 
3. **They leave "White Halos":** Simple thresholding tools delete pure white, leaving a jagged, ugly white border around anti-aliased curves.

### The Antigravity Breakthroughs
By acting as an Agent rather than a single-pass tool, we solved this by combining **math, visual feedback, and iteration**. 

#### 1. Alpha-Compositing Reverse Engineering
Instead of using AI to guess what is background, we use raw math. We calculate the Euclidean distance from pure white in 3D RGB space. For pixels on the edge of the logo (the anti-aliased pixels), we **reverse-engineer the alpha-blending math** (`C = (V - W*(1-a))/a`) to calculate what the original color *would have been* before it was blended with a white background, recovering the true colors and completely eliminating white halos.

#### 2. Local Variance Checkerboard Detection
Fake transparency checkerboards are a massive pain point. We solve it by utilizing `scipy`'s `uniform_filter` to calculate **local pixel variance**. Because a checkerboard consists of strictly alternating white and grey squares, it produces a very specific mathematical variance signature. By targeting that exact signature, we extract the checkerboard without accidentally deleting light-grey logo text.

#### 3. Agentic "Browser-in-the-Loop" Visual QA
We automated a visual testing pipeline. The agent generates an HTML file overlaying extracted logos on 5 harsh backgrounds (Navy, Green, Red, Yellow, Blue), deploys a Browser Sub-agent to take screenshots, visually inspects the results, and iteratively refines the algorithm bounds to achieve production-grade pixel perfection.
