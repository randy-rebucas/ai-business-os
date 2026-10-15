"""Colour math for workspace branding: WCAG 2.x contrast, hue-preserving lightness adjustment, logo palette extraction.

The derived accent must work where the app uses it — button fill under white text, link text on the page ground, the
focus ring — so it is adjusted until it meets 4.5:1 against the ground of each theme. The raw brand colour is kept
for decoration (the logo tile, the active-nav marker) and used only where it reaches 3:1 against what it sits on.
"""

import colorsys
from dataclasses import dataclass

# Platform grounds the accent must contrast with (frontend/src/app/globals.css). Keep in sync with the tokens.
LIGHT_BG = "#f4f6f5"
LIGHT_SHEET = "#ffffff"
DARK_BG = "#0c1412"
DARK_SHEET = "#121c1a"
# Accent text also lands on tinted surfaces (selected rows, panels): it is fitted against the least favourable one in
# each theme — the darkest light surface and the lightest dark surface — so it passes everywhere it can appear.
LIGHT_TEXT_GROUND = "#e2e8e5"   # --color-surface-2 (light)
DARK_TEXT_GROUND = "#1e2c28"    # --color-surface-2 (dark)
SHELL = "#0f3d36"          # the green rail (both themes)
INK = "#121a18"
WHITE = "#ffffff"
PLATFORM_ACCENT_LIGHT = "#1d6b5c"
PLATFORM_ACCENT_DARK = "#6fd1b6"

TEXT_AA = 4.5
NON_TEXT = 3.0


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) != 6:
        raise ValueError(f"not a #rrggbb colour: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _channel(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_value: str) -> float:
    r, g, b = hex_to_rgb(hex_value)
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hls(hex_value: str) -> tuple[float, float, float]:
    r, g, b = hex_to_rgb(hex_value)
    return colorsys.rgb_to_hls(r / 255, g / 255, b / 255)


def _from_hls(h: float, lightness: float, s: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, lightness)), s)
    return rgb_to_hex((r * 255, g * 255, b * 255))


def fit(hex_value: str, against: str, ratio: float) -> str:
    """The colour nearest in lightness (same hue and saturation) that reaches `ratio` against `against`: darkened on a
    light ground, lightened on a dark one. Returns the input when it already passes."""
    if contrast(hex_value, against) >= ratio:
        return hex_value.lower()
    h, lightness, s = hls(hex_value)
    step = -0.005 if luminance(against) > 0.18 else 0.005
    while 0.0 <= lightness <= 1.0:
        lightness += step
        candidate = _from_hls(h, lightness, s)
        if contrast(candidate, against) >= ratio:
            return candidate
    return INK if step < 0 else WHITE


def mix(fg: str, bg: str, amount: float) -> str:
    """`amount` of fg over bg (a flat tint)."""
    f, b = hex_to_rgb(fg), hex_to_rgb(bg)
    return rgb_to_hex(tuple(b[i] + (f[i] - b[i]) * amount for i in range(3)))


def is_chromatic(hex_value: str) -> bool:
    _, lightness, s = hls(hex_value)
    return s >= 0.25 and 0.12 <= lightness <= 0.92


NOTE_LIGHT = "#8a6210"   # brass note keys (globals.css --color-note)
NOTE_DARK = "#d9b25e"
INK_DARK = "#e8efec"


def _hue_gap(a: str, b: str) -> float:
    gap = abs(hls(a)[0] - hls(b)[0])
    return min(gap, 1 - gap) * 360


@dataclass(frozen=True)
class Accent:
    brand: str               # the logo's colour, unmodified
    light: str               # text accent, light theme: links, focus ring (≥ 4.5:1 on every light surface)
    on_light: str            # unused for text; kept for clients that fill with `light`
    fill_light: str          # button / selected fill, light theme: the brand itself whenever it can carry text
    on_fill_light: str       # text on that fill (ink or white, ≥ 4.5:1)
    soft_light: str          # 10 % tint for selected rows / soft badges
    dark: str                # text accent, dark theme (≥ 4.5:1 on every dark surface)
    on_dark: str
    fill_dark: str
    on_fill_dark: str
    soft_dark: str
    marker: str              # active-nav marker on the green shell (≥ 3:1 against it)
    note_light: str          # note-key colour: brass, or ink when the accent would be mistaken for a note key
    note_dark: str
    adjusted: list[str]      # human-readable notes for every change made for contrast


def _fill(brand: str, fallback: str) -> tuple[str, str]:
    """The brand as a fill when ink or white text reaches 4.5:1 on it; otherwise the contrast-fitted accent."""
    best = max((INK, WHITE), key=lambda t: contrast(t, brand))
    if contrast(best, brand) >= TEXT_AA:
        return brand, best
    return fallback, max((INK, WHITE), key=lambda t: contrast(t, fallback))


def derive(brand: str) -> Accent:
    brand = brand.lower()
    notes: list[str] = []
    light = fit(brand, LIGHT_TEXT_GROUND, TEXT_AA)
    if light != brand:
        notes.append(f"Links and focus use {light} — {brand} is too light for text on light backgrounds "
                     f"({contrast(light, LIGHT_TEXT_GROUND):.1f}:1 on the darkest surface).")
    dark = fit(brand, DARK_TEXT_GROUND, TEXT_AA)
    if dark != brand:
        notes.append(f"In the dark theme links use {dark} ({contrast(dark, DARK_TEXT_GROUND):.1f}:1).")
    on_dark = DARK_BG if contrast(DARK_BG, dark) >= TEXT_AA else WHITE
    fill_light, on_fill_light = _fill(brand, light)
    if fill_light == brand:
        notes.append(f"Buttons use your colour {brand} with {'dark' if on_fill_light == INK else 'white'} text "
                     f"({contrast(on_fill_light, brand):.1f}:1).")
    fill_dark, on_fill_dark = _fill(brand, dark)
    marker = fit(brand, SHELL, NON_TEXT)
    if marker != brand:
        notes.append(f"The navigation marker uses {marker} to stand out on the green rail.")
    close_to_note = _hue_gap(light, NOTE_LIGHT) < 25 and abs(hls(light)[1] - hls(NOTE_LIGHT)[1]) < 0.2
    if close_to_note:
        notes.append("Note numbers are set in ink so they aren't mistaken for links in your colour.")
    return Accent(brand=brand, light=light, on_light=WHITE, fill_light=fill_light, on_fill_light=on_fill_light,
                  soft_light=mix(light, LIGHT_SHEET, 0.1), dark=dark, on_dark=on_dark, fill_dark=fill_dark,
                  on_fill_dark=on_fill_dark, soft_dark=mix(dark, DARK_SHEET, 0.16), marker=marker,
                  note_light=INK if close_to_note else NOTE_LIGHT, note_dark=INK_DARK if close_to_note else NOTE_DARK,
                  adjusted=notes)


def platform_accent() -> Accent:
    a = derive(PLATFORM_ACCENT_LIGHT)
    return Accent(brand=PLATFORM_ACCENT_LIGHT, light=PLATFORM_ACCENT_LIGHT, on_light=WHITE,
                  fill_light=PLATFORM_ACCENT_LIGHT, on_fill_light=WHITE, soft_light=a.soft_light,
                  dark=PLATFORM_ACCENT_DARK, on_dark=DARK_BG, fill_dark=PLATFORM_ACCENT_DARK, on_fill_dark=DARK_BG,
                  soft_dark=mix(PLATFORM_ACCENT_DARK, DARK_SHEET, 0.16), marker="#c9a24a",
                  note_light=NOTE_LIGHT, note_dark=NOTE_DARK, adjusted=[])


def pick_brand(palette: list[dict]) -> str | None:
    """The most prominent chromatic colour of the logo (≥ 3 % of its visible pixels), or None for monochrome logos."""
    for entry in sorted(palette, key=lambda e: -e["share"]):
        if entry["share"] >= 0.03 and is_chromatic(entry["hex"]):
            return entry["hex"]
    return None
