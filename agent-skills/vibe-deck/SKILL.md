---
name: VibeDeck
description: Generate presentation slide images (PNG) using Python/Pillow with consistent visual quality, optional PPTX assembly, and speaker notes.
---

# VibeDeck Skill

Generate professional presentation slide images as PNG files using Python and Pillow,
then optionally assemble them into a branded PPTX with speaker notes.

## When to Use

- User asks to build a deck, presentation, or slide content
- User has existing Pillow slide scripts to follow as patterns
- User provides a topic outline or markdown document to turn into slides

## Related Workflow

> [!IMPORTANT]
> For the full end-to-end pipeline including **Visual QA checklist** and **PIL pitfall reference**,
> follow the `/slide-deck-generation` workflow (`~/.agents/workflows/slide-deck-generation.md`).
>
> Key steps in the workflow that complement this skill:
> 1. **Plan → Deck.md** — Clone approved content from the finalized plan into `<Topic>/Deck.md` as the single source of truth before generating slides
> 2. **Visual QA** — Mandatory `view_file` on every PNG after generation to catch rendering bugs (white-on-white text, clipping, Unicode failures)
> 3. **Speaker Notes** — Only created AFTER user approves the final visual slides

## Workflow

### Phase 0 — Collect deck-wide chrome FIRST (do not skip)

Before planning any content, **ask the user for the deck's global chrome and lock it into a
`DECK_META` block that EVERY slide script imports.** Skipping this is the #1 cause of a deck that
looks improvised — a session that doesn't ask will invent its own footer/branding per slide, and
the pieces won't match. Ask (with sensible defaults offered) for:

| Item | Why it must be decided up front | Default if user defers |
|---|---|---|
| **Footer text** | Runs on every content slide; must be identical everywhere | `"{Talk Title} · {Session/Venue}"` |
| **Branding** — logo PNG path, or a text wordmark, + where it sits | A logo added late means re-rendering every slide | text wordmark in footer, no logo image |
| **Page numbers** — on/off, start index, position | See the reconciled rule below — the delivery path decides this | on, bottom-right, title = no number, content starts at 1 |
| **Delivery format** — PNG-final vs PPTX-assembled | Determines WHERE chrome is baked (see below) | ask; if unsure, PNG-final |
| **Accent/brand color** | Ties section bands, rules, and title accent together | `C_BLUE` primary |
| **Aspect ratio** | 16:9 slides vs other | 16:9 (1920×1080) |

**The page-number reconciliation (resolves the apparent contradiction in Anti-Patterns):**
- **PNG-final delivery** (slides shown/exported straight from PNGs, no PPTX step) → footer + page
  number MUST be baked into every content-slide PNG via the shared `draw_chrome()` helper below.
  This is the common case for a talk deck delivered as images/PDF.
- **PPTX-assembled delivery** → do NOT bake page numbers into PNGs; `assemble_pptx.py` adds them
  as native PPTX fields. Baking them would double them up.

Write the answers into a `DECK_META` dict at the top of the shared setup, imported by every block
script, so footer/branding/page-number logic lives in ONE place and cannot drift between slides:

```python
DECK_META = {
    "footer": "{Talk Title} · {Conference or Venue} {Year}",
    "wordmark": None,              # or "Your Name" for a text brand in the footer
    "logo_png": None,             # absolute path to a logo PNG, or None
    "page_numbers": True,          # bake into PNG (PNG-final) — False if PPTX-assembled
    "page_start": 1,               # first CONTENT slide number (title carries none)
    "accent": "#1976D2",
    "delivery": "png-final",      # or "pptx"
}
```

### Phase 1 — Plan the Deck (Markdown Proposal)

1. **Research the topic.** Read all relevant source files the user points to.
2. **Create a deck proposal markdown** in the output directory with this structure:
   - YAML frontmatter (title, session, duration, audience)
   - Deck summary table (blocks, topics, slide ranges, timing)
   - For each slide:
     - **Slide N: Title (X min)** header
     - **Content:** — what appears on the slide (tables, diagrams, code, bullet points)
     - **Speaker Notes:** — what the presenter says (blockquote format)
   - Timing breakdown table at the end
   - Appendix for follow-ups / out-of-scope items
3. **Include an Agenda/TOC slide as slide 2** (optional but recommended for any deck >6 slides, or
   any talk with timed sections / a live demo). It's the "here's the flow" map — see the Agenda
   pattern in Visual Element Patterns below. Propose it in the plan so the user can opt out.
4. **Get user approval** before generating images. Approval covers content AND the `DECK_META`
   chrome from Phase 0.

> [!TIP]
> **After approval, parallelize the block generation across subagents.** Once the plan + DECK_META
> are approved and Block A's visual style is locked (see the Early User Gate below), the remaining
> blocks are independent, well-scoped rendering jobs — the ideal subagent fan-out. Dispatch one
> subagent per block **in parallel** (each imports the SAME `DECK_META` + design constants, so
> chrome stays identical), and suggest running them in **Auto mode** (`--permission-mode` auto /
> `dangerouslyskip`-free autonomy) since the work is pure local Pillow rendering into the output
> dir — no destructive ops, no network. Each subagent runs its own PNG-first QA loop before
> returning. The orchestrator then does the final cross-deck consistency pass (chrome matches,
> no two adjacent slides share a layout, page numbers sequential). Keep Block A on the main
> session for the style-approval gate; fan out B/C/… only after style is locked.

### Phase 2 — Generate Slide Images (Python/Pillow)

#### Design System

All slides must follow these constants:

```python
# Canvas
SLIDE_W, SLIDE_H = 1920, 1080  # 16:9 Full HD

# Cross-platform font detection
import platform

if platform.system() == "Darwin":  # macOS
    FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"
    BOLD_FONT_PATH = "/System/Library/Fonts/HelveticaNeue.ttc"
    MONO_FONT_PATH = "/System/Library/Fonts/Menlo.ttc"
elif platform.system() == "Linux":
    FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    BOLD_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    MONO_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
else:  # Windows
    FONT_PATH = "C:/Windows/Fonts/arial.ttf"
    BOLD_FONT_PATH = "C:/Windows/Fonts/arialbd.ttf"
    MONO_FONT_PATH = "C:/Windows/Fonts/consola.ttf"

# Font Sizes
font_title     = ImageFont.truetype(BOLD_FONT_PATH, 48, index=1)   # Slide title
font_header    = ImageFont.truetype(BOLD_FONT_PATH, 34, index=1)   # Section headers
font_text      = ImageFont.truetype(FONT_PATH, 26)                  # Body text
font_small     = ImageFont.truetype(FONT_PATH, 22)                  # Captions / footnotes
font_large_bold = ImageFont.truetype(BOLD_FONT_PATH, 32, index=1)  # Card titles
font_code      = ImageFont.truetype(MONO_FONT_PATH, 18)            # Code blocks
font_code_sm   = ImageFont.truetype(MONO_FONT_PATH, 16)            # Code annotations
font_label     = ImageFont.truetype(BOLD_FONT_PATH, 22, index=1)   # Labels / badges
font_medium    = ImageFont.truetype(FONT_PATH, 24)                  # Table cells
font_medium_bold = ImageFont.truetype(BOLD_FONT_PATH, 24, index=1) # Table headers

# Color Palette
C_BLUE       = "#1976D2"    # Block A / primary
C_BLUE_DARK  = "#0D47A1"
C_BLUE_LIGHT = "#E3F2FD"
C_GREEN      = "#2E7D32"    # Block B / success
C_GREEN_LIGHT = "#E8F5E9"
C_ORANGE     = "#E65100"    # Block C / warning
C_ORANGE_LIGHT = "#FFF3E0"
C_TEAL       = "#20B2AA"    # Recommendations
C_TEAL_DARK  = "#008080"
C_PURPLE     = "#6A1B9A"    # Code variables
C_DARK_BG    = "#1A1C29"    # Code blocks
C_GRAY_BORDER = "#CCCCCC"
C_WHITE      = "#FFFFFF"
C_BLACK      = "#000000"
C_TEXT       = "#333333"    # Body text
C_TEXT_LIGHT = "#666666"    # Subtitle / captions
```

> [!NOTE]
> On Linux, `.ttc` fonts use `index=0` (no index parameter needed).
> The `index=1` parameter is macOS-specific for HelveticaNeue Bold.
> Wrap font loading in a try/except to fall back to `ImageFont.load_default()`.

#### Script Structure

Organize scripts by block (3-5 slides each) to keep them manageable:

```
generate_slides_block_a.py   # Slides 1-4
generate_slides_block_b.py   # Slides 5-8
generate_slides_block_c.py   # Slides 9-12
```

> [!IMPORTANT]
> **Early User Gate — Show Block A PNGs After AI QA Is Complete**
>
> After generating Block A (Slides 1-4):
> 1. **AI completes its full QA cycle first** — `view_file` every PNG, fix all
>    clipping/overflow/contrast issues, regenerate, re-verify until zero defects
> 2. **Then show the polished PNGs to the user** for style/direction approval
>
> The user validates:
> - Visual style and color palette
> - Layout patterns and information density
> - Font readability and text sizing
> - Overall design direction
>
> **Only proceed to Block B and C after user approves Block A.**
> Never show unpolished first-draft PNGs — the AI QA loop must be complete first.
> Generating all 12 slides before getting feedback wastes effort if the user
> wants a different visual direction.

Each script must include:
- Import and font setup at the top
- Color constants
- Helper functions: `draw_rounded_rect()`, `create_slide(title)`, `draw_arrow_right()`, `draw_arrow_down()`
- One section per slide, clearly commented with `# ====... SLIDE N: Title ...====`
- Save to the same directory as the script with naming: `Slide_NN_Short_Name.png`

#### Helper Functions (copy into each script)

```python
def draw_rounded_rect(draw, xy, cornerradius, fill, outline, width=1):
    """xy = (x, y, w, h) — NOT (x1, y1, x2, y2)"""
    x, y, w, h = xy
    draw.rounded_rectangle([x, y, x+w, y+h], radius=cornerradius,
                           fill=fill, outline=outline, width=width)

def create_slide(title):
    """White 1920x1080 canvas with title and blue rule."""
    img = Image.new("RGBA", (SLIDE_W, SLIDE_H), C_WHITE)
    draw = ImageDraw.Draw(img)
    draw.text((60, 35), title, fill=C_BLACK, font=font_title)
    draw.rectangle([60, 95, 1860, 98], fill=C_BLUE)
    return img, draw

def draw_arrow_right(draw, x1, cy, x2, color, head_size=12):
    draw.rectangle([x1, cy-3, x2, cy+3], fill=color)
    draw.polygon([(x2-5, cy-head_size), (x2-5, cy+head_size),
                  (x2+head_size, cy)], fill=color)

def draw_arrow_down(draw, cx, y1, y2, color, head_size=12):
    draw.rectangle([cx-3, y1, cx+3, y2], fill=color)
    draw.polygon([(cx-head_size, y2-5), (cx+head_size, y2-5),
                  (cx, y2+head_size)], fill=color)

def draw_chrome(draw, page_num=None):
    """Deck-wide footer + branding + page number. Call ONCE at the end of every
    CONTENT slide (skip on the title slide) so every slide shares identical chrome.
    Reads DECK_META so footer/brand/page-number logic lives in one place — this is
    what stops per-slide improvisation. For PPTX-assembled delivery, pass page_num=None
    and set DECK_META['page_numbers']=False (PPTX adds numbers natively)."""
    # Footer (left)
    if DECK_META.get("footer"):
        draw.text((60, SLIDE_H - 42), DECK_META["footer"],
                  fill=C_TEXT_LIGHT, font=font_small)
    # Text wordmark (right of footer) — only if no logo image
    if DECK_META.get("wordmark") and not DECK_META.get("logo_png"):
        wm = DECK_META["wordmark"]
        w = draw.textlength(wm, font=font_small)
        draw.text((SLIDE_W - 60 - w - 90, SLIDE_H - 42), wm,
                  fill=C_TEXT_LIGHT, font=font_small)
    # Page number (bottom-right) — only when baking into PNG (PNG-final delivery)
    if DECK_META.get("page_numbers") and page_num is not None:
        n = str(page_num)
        w = draw.textlength(n, font=font_small)
        draw.text((SLIDE_W - 60 - w, SLIDE_H - 42), n,
                  fill=C_TEXT_LIGHT, font=font_small)
    # Logo image, if provided (bottom-right corner, above page number)
    if DECK_META.get("logo_png"):
        try:
            logo = Image.open(DECK_META["logo_png"]).convert("RGBA")
            lw = 180; lh = int(logo.height * lw / logo.width)
            logo = logo.resize((lw, lh))
            # caller must paste on the image, not the draw obj — see note
        except Exception:
            pass
```

> [!NOTE]
> `draw_chrome` draws footer/wordmark/page-number on the `draw` object. A logo *image* must be
> `img.paste(logo, (x, y), logo)` on the Image, not the ImageDraw — do that paste right after the
> `draw_chrome` call on slides that need it. Everything else is centralized so it can't drift.

#### Visual Element Patterns

##### Tables

```python
# Table with colored header row and alternating row colors
col_widths = [300, 500, 300, 240]  # Adjust per content
col_x = [80]
for w in col_widths[:-1]:
    col_x.append(col_x[-1] + w)
row_h = 48

# Header
draw_rounded_rect(draw, (col_x[0], table_y, sum(col_widths), row_h),
                  5, fill=C_BLUE, outline=C_BLUE)
for i, h in enumerate(headers):
    draw.text((col_x[i]+10, table_y+12), h, fill=C_WHITE, font=font_medium_bold)

# Data rows
colors_alt = ["#F4F8FC", "#FFFFFF"]
for i, row in enumerate(rows):
    y = table_y + row_h + i * row_h
    draw_rounded_rect(draw, (col_x[0], y, sum(col_widths), row_h),
                      0, fill=colors_alt[i%2], outline=C_GRAY_BORDER, width=1)
    for j, cell in enumerate(row):
        draw.text((col_x[j]+10, y+12), cell, fill=C_TEXT, font=font_medium)
```

##### Cards with Header Bar

```python
card_w, card_h = 530, 600
draw_rounded_rect(draw, (x+4, y+4, card_w, card_h), 15,
                  fill="#E0E0E0", outline="#E0E0E0")  # Shadow
draw_rounded_rect(draw, (x, y, card_w, card_h), 15,
                  fill=C_WHITE, outline=C_GRAY_BORDER, width=2)  # Body
draw_rounded_rect(draw, (x, y, card_w, 65), 15,
                  fill=color, outline=color)  # Header bar
draw.rectangle([x, y+40, x+card_w, y+65], fill=color)  # Square off bottom
draw.text((x+20, y+15), title, fill=C_WHITE, font=font_large_bold)
```

##### Code Blocks

```python
draw_rounded_rect(draw, (80, code_y, 1760, code_h), 10,
                  fill=C_DARK_BG, outline="#333344", width=2)
# Use font_code (Menlo 18) for content
# Colors: "#6A9955" for comments, "#569CD6" for XML tags,
#         "#CE9178" for values/strings, "#DCDCAA" for highlight lines
```

##### Agenda / TOC slide (slide 2 — the "flow" map)

The map of the talk: full-width colored **section bands**, each holding numbered items with a bold
title + a dim inline description. A top-right meta line gives the time budget; a bottom center-line
gives the one-sentence "where the climax is." This is the pattern a session should REUSE, not
reinvent — it's why Phase 0 collects the accent color and Phase 1 proposes this slide.

```python
# Top-right time budget (aligned to the title baseline)
budget = "60 min: ~25 slides + ~25 demo + ~10 Q&A"
bw = draw.textlength(budget, font=font_header)
draw.text((1860 - bw, 48), budget, fill=C_ORANGE, font=font_header)

# Sections: each = (band_label, band_color, [(n, title, desc), ...])
SECTIONS = [
    ("FOUNDATIONS  (~7 min)", C_BLUE, [
        ("1", "A Clash of Titans", "Title"),
        ("2", "Today's flow", "TOC (you are here)"),
    ]),
    ("THE REAL CASE  (~30 min, includes LIVE DEMO)", C_ORANGE, [...]),
    ("ROADMAP + Q&A  (~13 min)", C_GREEN, [...]),
]

y = 190
for band_label, band_color, items in SECTIONS:
    # Full-width section band (rounded, filled)
    draw_rounded_rect(draw, (60, y, 1800, 46), 8, fill=band_color, outline=band_color)
    draw.text((84, y + 9), band_label, fill=C_WHITE, font=font_large_bold)
    y += 46 + 24
    for n, title, desc in items:
        # Short color tab on the left echoing the band color
        draw_rounded_rect(draw, (60, y + 4, 8, 30), 4, fill=band_color, outline=band_color)
        draw.text((92, y), n + ".", fill=C_ORANGE, font=font_large_bold)   # number in accent
        draw.text((160, y), title, fill=C_WHITE, font=font_large_bold)     # bold title
        tw = draw.textlength(title, font=font_large_bold)
        draw.text((160 + tw + 30, y + 4), desc, fill=C_TEXT_LIGHT, font=font_medium)  # dim desc
        y += 52
    y += 28   # gap between sections

# Bottom center-line (the "climax is here" hint) + then draw_chrome for footer/page num
hint = "Live demo on the dummy branch — slides 8-9 are the climax."
hw = draw.textlength(hint, font=font_medium)
draw.text(((SLIDE_W - hw) / 2, 1015), hint, fill=C_ORANGE, font=font_medium)
draw_chrome(draw, page_num=1)   # the agenda IS content slide 1 → carries chrome
```

Rules for the agenda: keep it to **3 sections max**, **≤12 items total** (it's a map, not the
deck); "you are here" marker on the agenda's own row; the bottom hint names the single most
important beat so the room knows what to wait for. Section-band colors should be the SAME colors
those sections' content slides use later (color = meaning, deck-wide).

##### Recommendation / Takeaway Bar

```python
draw_rounded_rect(draw, (80, rec_y, 1760, 55), 10,
                  fill=C_TEAL, outline=C_TEAL_DARK, width=2)
draw.text((100, rec_y+12), "Recommendation: ...",
          fill=C_WHITE, font=font_label)
```

#### Common Pitfalls & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Text overflow into next column | Column too narrow for content | Widen column OR shorten text |
| Bullets clipped by card edge | Card height too small for vertical list | Increase card height or reduce line spacing |
| Code block clipped at slide bottom | code_h too large | Reduce code_h, verify `code_y + code_h < 1050` |
| Emoji render as boxes | macOS Pillow doesn't render emoji | Use text labels instead (e.g., "RECOMMENDED") |
| Unicode arrows rendering as squares | System fonts failing to map Unicode | Use ASCII alternatives (`->` instead of `→`) |
| Text overlaps next element | Y-position math error | Verify: `element_y + element_h + gap < next_element_y` |
| Bold text measured with regular font | `getlength()` uses wrong font | Use the **same font** for measurement and rendering |
| White text on white bg | `fill=color` variable matches background | Hardcode contrasting colors for text fill |

#### Design Intelligence

> [!IMPORTANT]
> This section encodes the **design judgment** required to produce professional slides.
> It targets frontier models (GPT-4/5, Sonnet/Opus 4, Gemini 3.1 Pro).
> Every decision in this section must be applied — do not skip or simplify.

##### Step 1: Content Shape Analysis

Before writing ANY rendering code, classify each slide's content into a **shape**:

| Content Shape | Trigger | Layout Pattern |
|---|---|---|
| **Ordered sequence** | 3-5 items with inherent order (layers, phases, steps) | Stacked horizontal bands OR horizontal flow boxes |
| **Parallel options** | 2-4 items of equal weight to compare | Side-by-side cards with colored headers |
| **Matrix/grid** | Data with rows × columns structure | Table with alternating row colors |
| **Flow/pipeline** | Input → Process → Output chain | Horizontal arrow-connected boxes |
| **Hierarchy** | Parent → children relationship | Tree layout or nested boxes |
| **Code + explanation** | Policy XML, config, query with annotations | Code block (dark bg) + side annotations |
| **Before/After** | Two states to contrast | Two-column split with "BEFORE"/"AFTER" labels |
| **Single concept + details** | One big idea with supporting bullets | Large header card + detail list below |
| **Timeline** | Events across time | Horizontal timeline with milestone markers |
| **Summary/recommendations** | Takeaways or action items | Numbered recommendation bars with color coding |

**Decision rule:** If content matches multiple shapes, pick the one that is **least like the previous slide's layout.** Visual variety across the deck matters more than perfect shape matching.

##### Step 2: Spatial Layout Recipes

**Canvas:** 1920 × 1080 px. Usable area: x=[60, 1860], y=[110, 1050].

**Centering N items horizontally:**
```python
total_content = N * item_w + (N - 1) * gap
start_x = (SLIDE_W - total_content) // 2
for i in range(N):
    x = start_x + i * (item_w + gap)
```

**Common layouts (pre-computed):**

| Layout | item_w | gap | start_x | Items |
|---|---|---|---|---|
| 2-column | 840 | 60 | 90 | 2 |
| 3-column cards | 530 | 35 | 145 | 3 |
| 4-column flow | 360 | 80 | 20 | 4 |
| Full-width table | 1760 | — | 80 | 1 |
| 2/3 + 1/3 split | 1100 + 580 | 40 | 80 | 2 |

**Vertical stacking:**
```python
# For N items stacked vertically in usable area [110, 1050]
usable_h = 940
item_h = (usable_h - (N - 1) * gap) // N
for i in range(N):
    y = 110 + i * (item_h + gap)
```

**Bottom margin rule:** Last element must satisfy `element_y + element_h + 30 < 1080`.

##### Step 3: Element Density Limits

**Do NOT exceed these maximums per layout:**

| Layout Type | Max Elements | Max Text Lines | Notes |
|---|---|---|---|
| Cards (3-col) | 3 cards × 5 bullets | 15 lines total | Reduce card_h if fewer bullets |
| Table | 8 data rows | 8 + header | Beyond 8 rows, split into 2 slides |
| Flow boxes (4-col) | 4 boxes × 4 bullets | 16 lines total | Keep bullets to 3-4 words each |
| Stacked bands | 5 bands | 10 lines total | 2 lines per band max |
| Code block | 18 lines of code | 18 | Font 18px minimum for readability |
| Full slide (any) | — | 25 lines | Absolute max text on any slide |

**Density escape valve:** If content exceeds limits, split into two slides rather than shrinking fonts or cramming. A clean two-slide sequence beats one cluttered slide.

##### Step 4: Visual Polish Rules

**Depth & Dimensionality:**
- Shadows on cards: offset `(+4, +4)` with `#E0E0E0` fill
- Rounded corners: `10px` for containers, `15px` for cards, `25px` for pills/badges
- Header bars: fill top of card with color, square off bottom with `draw.rectangle`

**Color Discipline:**
- Max 3 colors per slide: one dominant, one supporting, one accent
- Same color = same meaning across entire deck (never reassign mid-deck)
- Block-level coloring: Block A = Blue, Block B = Green/Orange, Block C = Teal

**Typography Hierarchy:**
- Title (48px bold) → only the slide title, never elsewhere
- Header (34px bold) → section labels within a slide
- Body (24-26px) → readable content (never go below 22px)

**Whitespace:**
- 60px+ margins on all edges
- Don't fill every pixel — whitespace signals professionalism
- Leave breathing room between sections (40px+ vertical gaps)

##### Anti-Patterns (Hard Rules)

- ❌ Never repeat the same layout on consecutive slides
- ❌ Never use bullet lists on more than 2 slides in a 12-slide deck
- ⚠️ Page numbers: bake into PNGs via `draw_chrome()` ONLY for **PNG-final** delivery; for
  **PPTX-assembled** delivery, don't bake them (PPTX adds them natively — see Phase 0 reconciliation)
- ❌ Never let footer / branding / page-number logic live per-slide — it MUST come from the shared
  `DECK_META` + `draw_chrome()` so it's identical on every slide (per-slide chrome = the improvised
  look this skill exists to prevent)
- ❌ Never use emojis (render as boxes) — use text labels or colored badges
- ❌ Never include company/personal info unless explicitly specified
- ❌ Never use plain rectangles without rounded corners or shadows
- ❌ Never default to plain white for all backgrounds — tint dense slides with `#F5F7FA`
- ❌ Never assume a fix is correct without re-viewing the PNG

### Phase 3 — Quality Review (PNG-First Inner Loop)

> [!CAUTION]
> QA must be done on the **PNG files directly** using `view_file`. Do NOT convert to
> PDF or PPTX for QA — that loop is 10x slower and introduces rendering differences.
> The PNG is the source of truth for visual content.

After generating all PNGs, **review every single one:**

1. Open each PNG with `view_file`
2. Run through this checklist per slide:

#### Text Visibility
- [ ] No white-on-white text (common when `color` variable matches both outline and fill)
- [ ] No text same color as container background
- [ ] All text is legible with sufficient contrast

#### Text Clipping & Overflow
- [ ] No text extends beyond its containing box/card/cell boundary
- [ ] Table cell text fits within column widths
- [ ] Multi-line text doesn't overflow vertically past container height
- [ ] Verify: `text_width + (2 × padding) < container_width`

#### Font Measurement Consistency
- [ ] Font used in `getlength()` / `textbbox()` MATCHES the font in `draw.text()`
- [ ] Bold text measured with bold font, not smaller regular font

#### Unicode & Special Characters
- [ ] No empty boxes (□) or missing glyphs
- [ ] Replace emojis with text: `✅` → `[Y]`, `❌` → `[N]`, `⚠️` → `( ! )`, `➔` → `->`

#### Layout & Spacing
- [ ] No overlapping elements
- [ ] Consistent vertical spacing between rows/items
- [ ] Architecture diagram connectors align with source/target boxes
- [ ] Bottom margin: at least 30px below last element

#### Deck-wide chrome consistency (cross-slide — the improvisation guard)
- [ ] Footer text identical on every content slide (came from `DECK_META`, not retyped)
- [ ] Page numbers present + sequential on content slides; title slide carries none (PNG-final only)
- [ ] Branding/logo in the same position on every slide
- [ ] Section-band colors on the agenda match those sections' content-slide colors
- [ ] Chrome came from `draw_chrome()` — grep the block scripts: no per-slide footer/page-number literals

3. Fix and regenerate any slides with issues
4. Re-verify fixed PNGs — **never assume a fix is clean without visual re-verification**
5. Iterate until zero defects (typical: 2-4 rounds)

> [!WARNING]
> **Zero Tolerance for "Close Enough"**
> - Every text element is pass/fail. Either it fits fully inside its container, or it doesn't.
> - Fixes can introduce new bugs. Always re-inspect after every fix.
> - Do NOT mark QA complete until every slide has zero clipping, zero invisible text, zero overflow.

### Phase 4 — Speaker Notes

Create a standalone `Speaker-Notes.md` file with consistent format per slide:

```markdown
## Slide N: Title (X min)

**Opening:**
1-2 sentences to frame what's on screen.

**Key Points:**
- Bulleted talking points (prompts, not scripts)
- Mark live demo opportunities
- Map to target audience if roles differ

**Copyable Code (If applicable):**
\`\`\`
(Commands, policies, or queries the presenter can copy-paste for demos)
\`\`\`

**Transition:**
Bridge sentence to the next slide.
```

Rules:
- Every slide gets Opening + Key Points + Transition (last slide gets Closing instead)
- Include timing in each header
- Keep notes as prompts, not scripts — the presenter should talk naturally
- **ALWAYS attach copyable code snippets** when the slide references code/queries

### Phase 5 — PPTX Assembly (Optional)

> [!NOTE]
> This phase is optional. If the user just needs PNG slides, stop at Phase 4.
> PPTX assembly adds template branding, speaker notes injection, and page numbers.

Use the `scripts/assemble_pptx.py` reference script to assemble PNGs into a branded PPTX.
No external dependencies by default (stdlib only: `pathlib`, `shutil`, `zipfile`, `re`).
Optional: install `cairosvg` if you want SVG logo fallback without a template.

#### Configuration

```python
# ─── Required ─────────────────────────────────────────────
SLIDES = ["Slide_01_Title.png", "Slide_02_Overview.png", ...]
OUTPUT = Path("My-Presentation.pptx")
WORK_DIR = Path("<WORKSPACE>/tmp/pptx_assembly")

# ─── Template (optional) ──────────────────────────────────
TEMPLATE = Path("path/to/template.pptx")  # or None for plain PPTX
TITLE_LAYOUT = "slideLayout1.xml"         # Layout for title slide (page 0)
CONTENT_LAYOUT = "slideLayout45.xml"      # Layout for content slides

# ─── Title Slide (page 0 — text only, no PNG) ────────────
TITLE_SLIDE_ENABLED = None    # None = auto-detect | True = force on | False = force off
TITLE_TEXT = "Presentation Title"
SUBTITLE_TEXT = "Subtitle or session info"

# ─── Branding (all optional) ─────────────────────────────
BRANDING = {
    "enabled": True,                    # False = plain slides, no decorations
    "logo_image": "image17.png",        # Logo filename in template media/
    "logo_position": (196678, 4777740), # EMU (x, y)
    "logo_size": (995378, 365760),      # EMU (cx, cy)
    "logo_svg_path": None,              # SVG logo for non-template mode (needs cairosvg)
    "logo_png_path": None,              # PNG logo for non-template mode (preferred)
    "logo_px_w": 220,                   # Fallback logo width in pixels
    "logo_position_px": (60, 1002),     # Fallback logo position in pixels
    "logo_aspect": (1200, 360),         # Logo aspect ratio (width, height)
    "gradient_image": "image28.jpg",    # Background image filename
    "copyright_text": "© 2026 Your Company. All Rights Reserved.",
    "page_numbers": True,               # Auto slide numbers
    "page_number_start": 0,             # 0 = title is page 0, content starts at 1
    "notes_font_size": 1100,            # hundredths of a point (1100 = 11pt)
}
```

When `TITLE_SLIDE_ENABLED = None` (default — auto-detect):
- If `SLIDES[0]` filename contains "title" (case-insensitive), the text-only title page is **skipped**
- Otherwise, a text-only title page is generated as page 0
- This prevents the most common bug: duplicate title slides when SLIDES already has a title PNG

When `TITLE_SLIDE_ENABLED = False` (force off):
- No text-only title page is generated
- PNGs start at page 0 (or page 1 if `page_number_start = 1`)
- Use this when your SLIDES list already includes an AI-generated hero title PNG

When `BRANDING["enabled"] = False`:
- No logo, no copyright text, no gradient background
- Plain white slides with PNG content and speaker notes only

#### Assembly Process

1. Unpack template `.pptx` (it's a ZIP file)
2. Create title slide (page 0) using template layout — text only, no page number
3. For each PNG: create a content slide XML with embedded decorations
4. Parse `Speaker-Notes.md` and inject as notesSlide XML
5. Update `presentation.xml`, `[Content_Types].xml`, and all `.rels` files
6. Clean unreferenced files and repack into `.pptx`

#### Post-Assembly Verification

After assembly, do ONE final check (not the inner QA loop):
- Open the PPTX in PowerPoint (or LibreOffice headless → PDF → `pdftoppm` for automated check)
- Verify: decorations render, page numbers are correct, speaker notes present

### Phase 6 — Commit

```bash
git checkout -b feat/{topic}-deck
git add {output-dir}/
git commit -m "feat({session}): add {topic} deck

- Deck proposal markdown (N slides, M-min session)
- Python slide generators (Pillow)
- N slide PNG images (1920x1080)
- Speaker notes
- PPTX assembly (optional)"
```

## Output Files

For a deck named `{topic}`:

```
{output-dir}/
├── {Topic}-Deck.md                    # Deck proposal + content
├── Speaker-Notes.md                   # Per-slide speaker notes
├── generate_slides_block_a.py         # Block A generator
├── generate_slides_block_b.py         # Block B generator
├── generate_slides_block_c.py         # Block C generator
├── assemble_pptx.py                   # PPTX assembly (optional)
├── Slide_01_Short_Name.png            # Generated images
├── Slide_02_Short_Name.png
├── ...
└── {Topic}.pptx                       # Assembled PPTX (optional)
```

## Reference Implementation

- `scripts/assemble_pptx.py` — Generic PPTX assembly with configurable branding
- Look for existing `generate_slides_block_*.py` in the project for PIL patterns
