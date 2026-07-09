# Prompt Patterns for Slide-Deck Heroes

Recipes for the most common image-generation use cases when building presentations. Each pattern explains:
- **When to use** — content shape that calls for this pattern
- **Recipe** — the prompt structure that works
- **Avoid** — what NOT to ask for (especially in-image text)
- **Leave for overlay** — what should be added in PPTX/Pillow, not baked into AI output

---

## Pattern 1 — Cinematic Hero (epic establishing shot)

**When to use:** Title slides, section openers, "this is the moment we're talking about" framing.

**Recipe:**
```
A wide cinematic shot, 16:9. {SUBJECT — what's centered in frame}. Storm clouds, distant lightning, volumetric god-rays piercing the sky. Cinematic chiaroscuro, dramatic side-lighting, ultra-photoreal Wētā Workshop quality, 8K detail, anatomically grounded — NOT comic-book or video-game styling. Composition: {SUBJECT} framed centrally with substantial sky above for slide-title overlay area. Mood: weighty, professional, momentous — Denis Villeneuve cinematography, not fantasy-game cover art. No text in the image.
```

**Avoid:**
- "Photo-realistic" alone — too vague; specify lighting + reference (Villeneuve, Nolan, Wētā)
- "Epic" without grounding — produces video-game art. Anchor with "anatomically grounded" + cinematographer reference
- In-image text or signage

**Leave for overlay:** title, subtitle, footer, page number.

---

## Pattern 2 — Dual-Arena Composition (two specialists, one shared artifact)

**When to use:** Slides about contrast, dialectic, or the doer/gatekeeper pattern. Use when you want the visual to literally show "two things facing each other across a third thing."

**Recipe:**
```
Vast cathedral-scale dark interior space, photoreal cinematic 16:9 ultra-wide. Two massive monolithic obelisks dominate the frame, each roughly 85 percent of image height — the LEFT monolith fills the left third (matte cobalt-blue stone, surface densely etched with {LEFT-METAPHOR-SYMBOLS}, lit from above by a focused cold blue spotlight casting a long pool on the floor), and the RIGHT monolith fills the right third (matte deep-crimson stone, surface densely etched with {RIGHT-METAPHOR-SYMBOLS}, lit from above by a focused warm red spotlight). Between them, suspended in the dark central void at chest height, a single brilliantly luminous horizontal {ARTIFACT — diff bar, scroll, beam} — pure white core fading to soft cyan edges, approximately one-third the image width. Reflective polished obsidian floor with crisp reflections. Volumetric atmospheric haze. Style: Blade Runner 2049 production design, ultra-clean photorealism, dramatic chiaroscuro, 4K detail. Composition: monoliths fill left and right thirds with substantial central negative space; artifact dead-centered. No text in the image.
```

**Avoid:**
- More than two main subjects — turns into clutter
- Asymmetric color choices — left/right symmetry is the visual contract
- In-image labels for the monoliths (use Pillow text overlay below the hero)

**Leave for overlay:** monolith labels, artifact label, slide title.

---

## Pattern 3 — Mythological Figures (recognizable but not gamey)

**When to use:** Title slides where you want a memorable, "talkable" hero metaphor (e.g., "two titans clashing").

**Recipe:**
```
Wide cinematic 16:9, photoreal. Two colossal humanoid figures in tense standoff on a high plateau at dusk, NOT mid-fight — the moment of debate, weapons LOWERED, focused on the artifact between them. Left figure: forged from {MATERIAL-A — luminous translucent circuit-board / weathered marble / iron}, with deep cobalt-blue light flowing through internal veins. Right figure: forged from {MATERIAL-B — molten copper / black obsidian / cracked granite}, warm amber-orange light glowing through internal seams. Both figures lean forward intently, eyes locked on a single glowing horizontal artifact suspended at chest height between them. Sky: heavy storm clouds with distant lightning, but no active strikes near the figures. Volumetric god-rays from breaking sky illuminate the artifact. Cinematic chiaroscuro, dramatic side-lighting, ultra-photoreal Wētā Workshop quality, 8K detail, anatomically grounded — NOT comic-book or video-game styling. Composition: figures framed left and right thirds, artifact dead-centered at mid-height, large negative space in upper third for slide title overlay. Mood: weighty, professional, momentous — Denis Villeneuve cinematography, not fantasy-game cover art. No text in the image.
```

**Avoid:**
- "Warriors", "battle", "clash" — produces World of Warcraft art. Use "standoff", "debate", "moment of contest"
- Active combat poses — locked weapons drift toward gaming aesthetic
- Bright primary colors without grounding — anchor with "matte / weathered / molten" + materiality

**Leave for overlay:** title, subtitle, presenter credit.

---

## Pattern 4 — Minimalist Architectural (clean isometric)

**When to use:** Corporate/executive decks. Sections about systems, architecture, structure. When the brand requires restraint.

**Recipe:**
```
Minimalist isometric architectural rendering, 16:9. {SUBJECT — two opposing glass towers / a single elevated platform / a stepped pyramid of layers} on a polished black surface. {LEFT-COLOR-OBJECT}: cool ice-blue glass, internally lit, geometric structure visible inside. {RIGHT-COLOR-OBJECT}: warm amber glass, internally lit. Between them, a single horizontal beam of pure white light spanning the gap. Background: deep gradient navy-to-black, distant subtle grid suggesting data space. Studio-quality product-render lighting, sharp shadows, Apple keynote aesthetic, dieter-rams design language. Style: minimalist 3D render, ultra-clean, luxury product launch visual. No text in the image.
```

**Avoid:**
- "Cinematic" or "epic" qualifiers — fights the minimalism
- Volumetric haze, god-rays — those are for cinematic patterns
- More than 3 colors

**Leave for overlay:** title, subtitle, callouts on each tower/object.

---

## Pattern 5 — Icon / Badge (single symbol on solid background)

**When to use:** Footer icons, section dividers, small in-line marks. NOT for hero use.

**Recipe:**
```
A single {SYMBOL — diff arrow / abstract circuit knot / wave glyph} centered on a solid {BG_COLOR} background. Soft glow around the symbol. Studio lighting, no other elements. {ASPECT 1:1 or 16:9}. Minimalist vector aesthetic, suitable for use as an icon at small sizes. No text.
```

**Avoid:**
- Detailed scenes — defeats the purpose
- Multiple symbols — pick one
- Photo-real backgrounds

**Leave for overlay:** any label or caption.

---

## Universal Rules (apply to every pattern)

1. **Always end the prompt with: `No text in the image.`** AI text rendering is unreliable for stylized titles. Bake nothing the speaker might want to edit.
2. **Specify aspect ratio in the prompt AND in the API call.** Belt and suspenders.
3. **Anchor mood with a specific cinematographer or design house** (Villeneuve, Nolan, Wētā Workshop, Apple keynote, dieter rams). Generic "cinematic" or "professional" produces stock art.
4. **Reserve negative space** for overlays: top third for slide titles, bottom-left for branding, bottom-right for page numbers.
5. **Iterate at 1K tier (~$0.04)** until composition is locked. Only generate at 4K (~$0.24) for final winner.
6. **Generate 2–4 directions per slide.** First-try output is rarely the best one.

---

## Cost Math (refresh)

| Tier | Resolution (16:9) | Tokens | Cost |
|---|---|---|---|
| 1K | 1376×768 | ~1500 | ~$0.04 |
| 2K | (scaled) | ~2000 | ~$0.08 |
| 4K | 3840×2160 | ~3000 | ~$0.24 |

Typical 10-hero deck: ~$2.70 total (30 explorations + 10 locked + 3 finals).
