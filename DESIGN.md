---
name: AI Business OS
description: AI employees you can audit. Agent output is set like an audited annual report, with figures whose notes lead to the evidence.
colors:
  paper: "#f4f6f5"
  sheet: "#ffffff"
  surface: "#edf1ef"
  surface-2: "#e2e8e5"
  border: "#d3dcd8"
  border-strong: "#b4c1bc"
  ink: "#121a18"
  muted: "#46534e"
  subtle: "#55625d"
  accent: "#1d6b5c"
  accent-strong: "color-mix(in oklab, #1d6b5c 82%, #000)"
  accent-fill: "#1d6b5c"
  accent-fill-strong: "color-mix(in oklab, #1d6b5c 86%, #000)"
  on-accent-fill: "#ffffff"
  accent-soft: "#e8f0ee"
  note-brass: "#8a6210"
  rail-brass: "#c9a24a"
  rail: "#0f3d36"
  rail-2: "#1a4a42"
  rail-fg: "#e9f2ef"
  rail-muted: "#a9c6be"
  info: "#1d5fb0"
  success: "#0e6b4f"
  warning: "#8f5b00"
  danger: "#b42335"
  dark-paper: "#0c1412"
  dark-sheet: "#121c1a"
  dark-surface: "#17231f"
  dark-surface-2: "#1e2c28"
  dark-border: "#263632"
  dark-border-strong: "#3a4f48"
  dark-ink: "#e8efec"
  dark-muted: "#a7b8b2"
  dark-subtle: "#8fa29b"
  dark-accent: "#6fd1b6"
  dark-accent-soft: "#1a332d"
  dark-note-brass: "#d9b25e"
  dark-rail: "#0a2a25"
  dark-rail-2: "#12352f"
  dark-info: "#7cb7ff"
  dark-success: "#4fd1a5"
  dark-warning: "#f5c065"
  dark-danger: "#f58a97"
typography:
  display:
    fontFamily: "Schibsted Grotesk, Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "64px"
    fontWeight: 800
    lineHeight: 1.02
    letterSpacing: "-0.025em"
  figure:
    fontFamily: "Schibsted Grotesk, Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "64px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.025em"
    fontFeature: "\"tnum\" 1"
  figure-md:
    fontFamily: "Schibsted Grotesk, Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "44px"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.025em"
    fontFeature: "\"tnum\" 1"
  headline:
    fontFamily: "Schibsted Grotesk, Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "32px"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Schibsted Grotesk, Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.55
    letterSpacing: "-0.025em"
  title-sm:
    fontFamily: "Schibsted Grotesk, Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.43
  body-lg:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.55
  button:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.43
  label:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.45
    letterSpacing: "0.08em"
  label-rail:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.45
    letterSpacing: "0.12em"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, Cascadia Mono, monospace"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.43
rounded:
  sm: "2px"
  md: "3px"
  lg: "4px"
spacing:
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "7": "28px"
  "8": "32px"
  "10": "40px"
components:
  button-primary:
    backgroundColor: "{colors.accent-fill}"
    textColor: "{colors.on-accent-fill}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.accent-fill-strong}"
    textColor: "{colors.on-accent-fill}"
  button-secondary:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "36px"
  button-ghost:
    textColor: "{colors.muted}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "36px"
  button-ghost-hover:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  button-danger:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.danger}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "36px"
  input-field:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "36px"
  sheet:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.sm}"
  sheet-header:
    typography: "{typography.title-sm}"
    padding: "14px 20px"
  rail:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.rail-fg}"
    width: "256px"
  rail-nav-item:
    textColor: "{colors.rail-fg}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "6px 8px"
  rail-nav-item-active:
    backgroundColor: "{colors.rail-2}"
    textColor: "{colors.sheet}"
  table-head-cell:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    padding: "10px 16px"
  figure-value:
    textColor: "{colors.ink}"
    typography: "{typography.figure}"
  note-key:
    textColor: "{colors.note-brass}"
---

# Design System: AI Business OS

## Overview

**Creative North Star: "The Annual Report"**

Agent output is set like an audited annual report. A deep green rail holds the platform's chrome; the working area is cool paper with white sheets laid on it; heavy ink rules, not boxes, mark where a section, a figure row or a table begins. Figures are printed at report scale in a grotesk display face, and each one carries a small brass note key. Following the key opens a numbered note that says how the figure was counted and links to the records it came from. The figure is the claim and the note is the evidence; the whole system is built so neither appears without the other.

Density is operational, not decorative: 14px body text, tight row rhythm, tabular numerals everywhere numbers line up. Hierarchy comes from scale contrast (64px figures against 14px notes), ink weight and position, never from shadows or colour washes. State is always a glyph plus a word, so the report stays legible in greyscale and to anyone who cannot rely on hue.

The world is deliberately the opposite of the category default: no grid of identical white KPI cards, no indigo accent, no pill badges. It is also a white-label host. A workspace wears its own logo, an accent derived from that logo and one of five type moods, while the shell green, the brass, the ink rules and every status colour stay the platform's, so governance signals read the same in every company.

**Key Characteristics:**
- Deep report-green rail (`rail`) with a brass rule under the platform mark and a brass square marking the active page.
- Cool paper ground, white sheets, ink (`ink`) text and rules; 3px ink rules over page titles and figure rows, 2px over sections, table heads, tabs and notes.
- Report-scale figures (Schibsted Grotesk 800, tabular) with superscript brass note keys and a Notes list keyed 1…n.
- Square-ish corners (2–4px), flat surfaces, no shadows inside the app.
- States carry glyph + word; quantities against hard limits are capacity meters with an ink end mark.
- Tenant branding swaps accent and type mood only, within contrast rules enforced by the backend.

## Colors

A restrained green-and-paper palette: one deep green for the shell, one working accent for action, brass reserved for note keys, and four fixed status hues.

### Primary
- **Ledger Green** (`accent`, `accent-fill`): the platform's own accent and the default for every tenant-overridable action colour. As `accent` it is the text-and-focus tone (links, focus outline, caret, active tab underline, capacity fill); as `accent-fill` it fills primary buttons. On a branded workspace these two diverge (see Tenant Branding). `accent-strong` and `accent-fill-strong` are oklab mixes toward black for hover.
- **Ledger Tint** (`accent-soft`): text selection and selected-row tint. Never carries text that depends on it for contrast.

### Secondary
- **Report Green** (`rail`, `rail-2`): the shell. The 256px rail, the mobile top bar, the landing cover and the auth aside. `rail-2` is the active nav item's ground. Text on it is `rail-fg`, with `rail-muted` for group labels and secondary lines. In dark mode the rail deepens (`dark-rail`, `dark-rail-2`).

### Tertiary
- **Note Brass** (`note-brass`; `dark-note-brass` in dark): note keys and note numbers, the numerals of the landing contents page, and the dot on the platform mark on light grounds. Nothing else.
- **Rail Brass** (`rail-brass`): the 2px rule under the platform mark in the rail, the platform mark's dot on dark grounds, and the platform default for the active-nav marker.

### Neutral
- **Paper** (`paper`): the page ground behind everything.
- **Sheet** (`sheet`): white sheets, inputs, secondary buttons, the auth form, the logo tile in the rail.
- **Surface / Surface 2** (`surface`, `surface-2`): ghost-button hover, inset panels, empty meter tracks. `surface-2` is the least favourable light ground and the one tenant accents are fitted against.
- **Hairline / Strong Hairline** (`border`, `border-strong`): row dividers and sheet edges; control borders and neutral badges.
- **Ink** (`ink`): body text and the heavy report rules. The same value draws both, which is why rules read as print rather than as UI borders.
- **Muted / Subtle** (`muted`, `subtle`): descriptions and note text; context lines, captions, placeholders.

### Status (platform-fixed)
- **Info** (`info`), **Success** (`success`), **Warning** (`warning`), **Danger** (`danger`), with dark counterparts. Badges and alerts use the hue as text, a 35% border and a 10% fill.

### Tenant Branding
Set at runtime on `<html>` as `--brand-*` and `--mood-*` variables by the backend's colour math (`backend/abos/branding/colors.py`). Tenants may change only:
- **Accent text** (`--brand-accent-light/-dark`): the brand colour darkened (light theme) or lightened (dark theme), same hue and saturation, until it reaches 4.5:1 against `surface-2` of that theme, so it passes on every surface it can land on.
- **Accent fill** (`--brand-fill-*`, `--brand-on-fill-*`): the raw brand colour fills buttons whenever ink or white text reaches 4.5:1 on it (a yellow logo gives yellow buttons with ink text); otherwise the fitted accent fills them.
- **Accent tint** (`--brand-accent-soft-*`): 10% of the fitted accent over white (16% over the dark sheet).
- **Rail marker** (`--brand-marker`): the brand fitted to at least 3:1 against `rail`.
- **Note keys** (`--brand-note-*`): stay brass, unless the fitted accent is within 25° of hue and 0.2 lightness of brass, in which case note keys go to ink so they are not mistaken for links.
- **Type mood** (`--mood-display`, `--mood-text`): one of five curated pairings (see Typography).
- **Logo**: shown on a white 40px tile in the rail's workspace block (or the workspace initials on that tile).

Tenants may never change: the rail and its brass rule, paper/sheet/ink and the neutrals, the four status colours, the platform mark, radii, layout, or the type scale.

### Named Rules
**The Two Accents Rule.** Filled controls wear the brand itself when it can carry text at 4.5:1; links, focus and caret always use the contrast-fitted accent. Never use `accent-fill` as a text colour.

**The Constant Signals Rule.** Status hues, the green shell and the brass rule are the platform's in every workspace. A tenant accent never stands in for success, warning or danger.

**The Brass Is for Notes Rule.** Brass marks evidence: note keys, note numbers and the platform mark. It is never a button, link or decoration colour. Keep `note-brass` text on `paper` or `sheet` (5.0:1 on paper), never on `surface-2`.

## Typography

**Display Font:** Schibsted Grotesk (falls back to the text face, then system sans)
**Body Font:** Public Sans (with ui-sans-serif, system-ui)
**Label/Mono Font:** JetBrains Mono, for identifiers only (the `.ident` treatment, which also breaks anywhere so ids never break layouts)

**Character:** A heavy, compact news-grotesk for numerals and headings over a plain civic workhorse for reading; the pairing reads as a printed financial report rather than a dashboard.

### Hierarchy
- **Figure** (800, 64px at ≥640px / 52px below, line-height 1, -0.025em, tabular): report-scale figures in a figure row. A medium step (44px / 36px) for secondary figure rows. Units sit beside the numeral in the text face at 0.3em, 600, `muted`.
- **Display** (800, 64px at ≥640px / 44px below, line-height 1.02, -0.025em): the landing cover headline only.
- **Headline** (800, 32px at ≥640px / 28px below, line-height 1.25, -0.015em): page H1 under a 3px ink rule; landing and auth section statements (28–34px).
- **Title** (700, 18px, -0.025em): report-section headings. **Title-sm** (700, 15px): sheet headers and the Notes heading.
- **Body** (400, 14px, 1.43): all working text, table cells, notes. Descriptions cap at 42rem (`max-w-2xl`). Landing prose steps up to 18px.
- **Label** (600, 11px, uppercase, 0.08em): table column heads and filter labels. Rail group labels use 0.12em in `rail-muted`.
- **Note key** (700, 0.3em of the numeral it annotates, superscript, `note-brass`): em-sized so it scales with the figure.

### Type Moods
The platform voice is **Report** (Schibsted Grotesk / Public Sans). A workspace may wear one other curated pairing, matched from its industry or chosen by its owner: **Market** (Bricolage Grotesque / Figtree), **Works** (Archivo for both), **Care** (Source Serif 4 / Source Sans 3), **Studio** (Familjen Grotesk / Hanken Grotesk). Non-default moods are not preloaded.

### Named Rules
**The Report Scale Rule.** A headline figure is a numeral at report scale with a note key, set in a ruled figure row. It is never a number inside an identical white card.

**The Moods Swap Faces, Not Scale Rule.** A type mood replaces the two families and nothing else; sizes, weights, tracking and the hierarchy above are fixed.

**The Context Below Rule.** The period, department or time-zone line sits directly under the H1 (14px, 500, `subtle`), never as a label above the title.

## Layout

The app is a two-column frame: a sticky 256px green rail at ≥1024px, replaced below that by a 56px green top bar that opens a 288px drawer over a 50% black scrim. Content sits in a centred column capped at 72rem (`max-w-6xl`) with 16px side padding on phones, 24px at ≥640px, 40px at ≥1024px, and 32px top and bottom. Spacing follows a 4px base: 8 and 12px inside components, 16–24px between figure cells and table cells, 28px under the page header, 32px between report sections.

Figure rows are a definition-list grid that auto-fits columns of at least 11rem; cells are separated by vertical hairlines and stack below 640px. On wide screens the Notes list sits beside the figure row it annotates; on narrow screens it follows the row. Tables scroll horizontally inside their own wrapper rather than squeezing. Everything must hold at 390px.

The landing page is a report cover then a contents page: a green cover band with the headline and a specimen sheet that overhangs the band's bottom edge, then a numbered contents list (number, title + body, part name in a 9rem right column). Auth pages split into a green statement aside and a sheet on paper, collapsing to the sheet alone below 1024px.

## Elevation & Depth

The app is flat. Depth is conveyed by ground (paper vs. white sheet vs. green rail), by hairlines between rows, and above all by ink rules that start each unit of the report: a 3px rule over the page header and figure rows (and the top edge of the auth sheet and landing specimen), a 2px rule over report sections, Notes, table heads and tab strips. Motion is limited to state: colour transitions at 150ms, meter fills at 500ms on an exponential ease-out, and the note-arrive flash.

### Shadow Vocabulary
- **Specimen lift** (`box-shadow: 0 24px 48px -28px rgba(18,26,24,0.35)`): only the example report sheet on the landing cover, where a white sheet sits over the green band. Not used inside the app.

### Named Rules
**The Ink, Not Shadow Rule.** A unit of the report is announced by an ink rule above it, not by a box, a border all round or a shadow beneath it.

**The Note Arrives Rule.** A followed note key outlines its note in brass for 1.8s (2px outline, offset 2px, fading to transparent on the expo ease-out). An outline, not a fill: a tinted background would lower the contrast of the links inside the note. Reduced-motion users get the jump without the flash.

## Shapes

Corners are nearly square: 2px on buttons, inputs, badges, alerts, sheets and nav items; 3–4px only on a few inset lists and panels. Circles appear only in spinners. The capacity meter has no rounding at all, and its limit is a 2px ink end mark standing 4px proud of the track. The platform mark is a report sheet (an outlined rectangle with a heading bar and two text lines) with a brass dot at its top-right corner. Logos sit on a white tile because they are drawn for light grounds.

## Components

### Buttons
Quiet, rectangular and decisive.
- **Shape:** 2px corners; 32 / 36 / 44px heights (sm / md / lg), 12 / 16 / 24px side padding; 14px semibold (16px at lg); 16px icons with an 8px gap.
- **Primary:** `accent-fill` with `on-accent-fill` text and a 1px inset 10%-black ring so pale brand fills keep an edge on white; hover moves to `accent-fill-strong`.
- **Secondary:** white sheet, `border-strong` edge, ink text; hover sharpens the edge to ink.
- **Ghost:** `muted` text, no edge; hover gives a `surface` ground and ink text.
- **Danger:** white sheet, `danger` text, 50% danger edge; hover adds a 10% danger tint.
- **States:** press nudges down 1px; disabled is 50% opacity; loading shows an inline spinner and `aria-busy`.
- **On the green cover:** primary becomes a white button with rail-green text; ghost gets a 30%-white edge.

### Status Badges (chips)
- **Style:** 2px corners, 1px border in the status hue at 35%, 10% fill, 12px semibold text in the hue, preceded by a 12px glyph.
- **Glyphs:** success = check, info = info, warning/pending = dashed circle, danger/refused = struck circle, neutral = dash (neutral uses `surface` and `border-strong` with `muted` text).

### Alerts
The same tone recipe with a 16px icon, an optional semibold title and body text at 85% ink. Danger alerts are `role="alert"`, the rest `role="status"`.

### Sheets (Cards)
- **Corner Style:** 2px.
- **Background:** `sheet` on `paper`.
- **Shadow Strategy:** none (see Elevation).
- **Border:** 1px `border` hairline.
- **Header:** 14px × 20px padding, title-sm heading with an optional 12px muted description, hairline below.
- Prefer a flat Report Section over a sheet when content is a run of report material rather than a contained tool.

### Inputs / Fields
- **Style:** white, 1px `border-strong`, 2px corners, 36px tall (textarea min 96px), 12px side padding, `subtle` placeholder; hover deepens the edge to `subtle`.
- **Focus:** edge turns `accent` plus a 2px ring at 25% accent.
- **Error / Disabled:** `aria-invalid` edges turn `danger` with a 12px danger message below; disabled is 60% opacity. Labels are 14px medium ink above the control, hints 12px muted below.

### Navigation (the rail)
- **Structure:** 56px platform-mark header ruled 2px in rail brass; the workspace block (40px white logo tile or initials, name in white semibold, industry · role in `rail-muted`); grouped links; the signed-in user at the foot. The list fades out at its bottom edge to show it scrolls.
- **Items:** 14px `rail-fg` at 85%, 6px × 8px padding, 2px corners, 16px icon in `rail-muted`; hover gives 5% white ground and white text.
- **Active:** `rail-2` ground, white semibold text, a 6px square marker and the icon in the marker colour (`--brand-marker`, rail brass by default). Unread counts are white chips with rail-green text.
- **Mobile:** 56px green top bar with menu button and mark; the drawer is the same rail at 288px.

### Tabs
A strip ruled 2px in ink; tabs are 14px muted text with a 4px bottom bar, the selected tab ink semibold with an `accent` bar. Full WAI-ARIA keyboard behaviour (arrows, Home, End).

### Tables
No box of their own. The head is ruled 2px in ink with label-style column heads in `muted`; rows are 12px × 16px cells divided by hairlines; numerals are tabular.

### Capacity Meter
An 8px `surface-2` track filled in `accent` up to a hard ink end mark; at or over the limit the fill turns `danger` and the caption reads "limit reached" in semibold danger. Caption: "used of limit · n%". Exposed as `role="meter"` with a value text.

### Figures and Notes (signature)
The world's signature move. A **figure row** is a definition list under a 3px ink rule; each cell has a 14px semibold ink label, the figure numeral (tinted `warning` or `danger` only when the figure itself is a warning), an optional unit, a superscript **note key**, and an optional 12px muted detail line or capacity meter. The **Notes** section, under a 2px ink rule, lists each note as a brass number in a 1.5rem column followed by muted text that says how the figure was counted and a semibold accent link to the records ("Open the records"). Notes must describe real data and real links; a note key without a note, or a note without evidence, is a defect.

### Report Section
A heading under a 2px ink rule with content set flat on the paper, not boxed; an optional action aligns to the heading's baseline.

## Do's and Don'ts

### Do:
- **Do** start every page with the ink-ruled PageHeader: H1 at 28/32px 800, the context line beneath it, description capped at 42rem.
- **Do** put headline numbers in a Figures row with a NoteKey and a matching Notes entry that links to real records.
- **Do** pair every status colour with a glyph and a word, using the Badge recipe.
- **Do** show quantities against hard limits (budgets, daily runs) as a Capacity meter with its ink end mark.
- **Do** read action colour from `accent-fill` / `on-accent-fill` and text-accent colour from `accent`, so tenant branding flows through.
- **Do** keep every text pairing at 4.5:1 or better: light ink 16.3:1 on paper, muted 7.4:1, subtle 5.9:1 (5.1:1 on surface-2), note brass 5.0:1 on paper, platform accent 5.9:1 with white on it at 6.3:1, rail text 10.6:1, rail muted 6.6:1, rail marker 5.0:1; in dark mode every text token is at least 5.4:1 on every surface.
- **Do** keep the 2px accent focus outline (offset 2px) on every interactive element.

### Don't:
- **Don't** build grids of identical white KPI cards, use an indigo accent, or use pill-shaped badges.
- **Don't** put shadows on app surfaces; the specimen sheet on the landing cover is the only lift.
- **Don't** use brass for buttons, links or decoration, or set brass note text on `surface-2`.
- **Don't** let a tenant accent recolour status, the rail, the brass rule or the platform mark.
- **Don't** set a label or eyebrow above a page title; context goes under the H1.
- **Don't** convey state by hue alone.
- **Don't** round corners past 4px.
