# DESIGN.md — Communication PhD Program Explorer

Visual world: **broadcast test-card bars on a quiet studio ground.** One loud signature (the six colour bars) carries identity;
everything else is dense, legible, and operable. Light by default (people use this at a desk next to a document), dark honoured.

## Tokens (src/styles/global.css)
- Ground: `--bg #F6F6F3` / dark `#14161A`; panels `--bg-2`; insets `--bg-3`; ink `#16181D` / chalk `#E9EAE6`; three ink steps.
- Action: `--action #1F5FD6` (dark `#6EA4FF`). Used for primary buttons, links, focus rings, active map pins, filled signal bars.
- Lenses (semantic, never decorative): topic `#D9A800`, approach `#0A95A8`, data `#2C9657`, setting `#BF3A9A`, region `#3A68D8`; plus `--bar-red` for the sixth bar and errors.
- Radii: 10px controls, 14px panels. Elevation: one 1px border on resting surfaces; one offset soft shadow (`--shadow`) on floating surfaces (drawer, mobile nav). Never both.
- Motion: `--ease-out cubic-bezier(.16,1,.3,1)`; one authored moment (`.rise` on the results header). Reduced motion respected.

## Type
- Display: Bricolage Grotesque (variable; width 92% on h1), 600, tracking −0.02em, line-height 1.08.
- UI/body: Schibsted Grotesk 16px/1.55, tabular numerals on. Chinese UI falls back to the system CJK stack.
- Self-hosted woff2 in `public/fonts` (latin + latin-ext). No Google Fonts at runtime.

## Components
- `.brand` six-bar wordmark · `.sig` five-bar signal glyph next to every fit number · `.loadbar` six bars that light during model download.
- `.chip[data-dim]` lens-tinted label chips (square swatch, tinted ground); `.primary` adds weight and ★.
- `.row` person row (avatar · identity · side actions) shared by Match, Directory, Shortlist. `.drawer` right-side detail panel.
- `.seg` segmented control for view switches; `.facet` checklists with counts; `.pin` map markers.

## Rules
- No eyebrows/kickers, no all-caps labels, no emoji icons, no decorative gradients, no same-size card grids.
- Numbers align (tabular); scores always show the glyph + number together.
- Copy names the action ("Find matches", "Save", "Export CSV"); errors name the fix.
