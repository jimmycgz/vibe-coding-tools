---
title: frontmatter should be skipped, not flagged as setext
---

Setext Title Line One
Setext Title Line Two
===

# Heading with trailing backslash\

Normal paragraph line one
Normal paragraph line two — this is fine, ordinary soft-wrapped prose.

Line with one trailing space 
Next line right after it.

Line with a correct hard break  
Next line after the hard break.

```
fake --- underline inside a fence should not trigger
fake header
===
```

---

Above is a real thematic break (---), not a setext underline — should not flag.

**Speaker:** stacked bold labels with no separator
**Format:** will merge into one rendered line — should flag BOLD-LABEL-MERGE

- **List item field:** should NOT flag — this is a real list, not stacked bold lines
- **Second list item:** should NOT flag either

**Correctly separated field:**

**Because a blank line follows the one above — should NOT flag.**

