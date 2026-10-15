"""Phase 8 workspace branding: logo validation and re-encoding, palette extraction, WCAG-AA accent derivation for both
themes, type mood from industry, owner overrides, permissions and tenancy (ADR-035)."""

import io
import zipfile

import pytest
from PIL import Image, ImageDraw

from abos.branding import colors, moods
from tests.conftest import join


def png(fill="#f5c400", size=(240, 120), bg=(255, 255, 255, 0), extra: bytes = b"", fmt="PNG") -> bytes:
    img = Image.new("RGBA" if fmt == "PNG" else "RGB", size, bg if fmt == "PNG" else (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, size[0] - 20, size[1] - 20], fill=fill)
    d.rectangle([40, 50, size[0] - 40, 70], fill="#111111")  # a dark wordmark bar
    out = io.BytesIO()
    img.save(out, format=fmt)
    return out.getvalue() + extra


def upload(actor, data: bytes, name="logo.png"):
    return actor.client.post("/api/v1/org/branding/logo", files={"file": (name, data)}, headers=actor.h())


# ---- colour math -------------------------------------------------------------------------------------------------

def test_contrast_and_hue_preserving_fit():
    assert round(colors.contrast("#000000", "#ffffff"), 1) == 21.0
    yellow = "#f5c400"
    assert colors.contrast(yellow, colors.LIGHT_BG) < 2  # a yellow brand fails as text on the light ground
    fitted = colors.fit(yellow, colors.LIGHT_BG, 4.5)
    assert colors.contrast(fitted, colors.LIGHT_BG) >= 4.5 and colors.contrast("#ffffff", fitted) >= 4.5
    assert abs(colors.hls(fitted)[0] - colors.hls(yellow)[0]) < 0.02  # same hue, only lightness moved
    a = colors.derive(yellow)
    assert colors.contrast(a.dark, colors.DARK_BG) >= 4.5 and colors.contrast(a.on_dark, a.dark) >= 4.5
    assert colors.contrast(a.marker, colors.SHELL) >= 3.0
    assert any(n.startswith("Links and focus use") for n in a.adjusted)
    # The logo colour itself stays the button fill (with ink text) — the brand isn't lost to contrast fitting.
    assert (a.fill_light, a.on_fill_light) == ("#f5c400", colors.INK) and colors.contrast(a.on_fill_light, a.fill_light) >= 4.5
    assert a.note_light == colors.INK  # a brass-like accent would be confused with note keys
    blue = colors.derive("#0047ab")
    assert blue.fill_light == "#0047ab" and blue.note_light == colors.NOTE_LIGHT
    p = colors.platform_accent()
    assert colors.contrast(p.light, colors.LIGHT_BG) >= 4.5 and colors.contrast(p.dark, colors.DARK_BG) >= 4.5
    assert colors.contrast(p.marker, colors.SHELL) >= 3.0
    light_surfaces = ("#f4f6f5", "#ffffff", "#edf1ef", "#e2e8e5")  # globals.css: bg, bg-2, surface, surface-2
    dark_surfaces = ("#0c1412", "#121c1a", "#17231f", "#1e2c28")
    for hexv in ("#f5c400", "#0047ab", "#e60012", "#00a651", "#7b2d8e", "#ff6f00", "#00b5e2", "#222222", "#9be7ff"):
        d = colors.derive(hexv)
        assert min(colors.contrast(d.light, s) for s in light_surfaces) >= 4.5, hexv
        assert min(colors.contrast(d.dark, s) for s in dark_surfaces) >= 4.5, hexv
        assert colors.contrast(d.on_fill_light, d.fill_light) >= 4.5, hexv
        assert colors.contrast(d.on_fill_dark, d.fill_dark) >= 4.5 and colors.contrast(d.on_dark, d.dark) >= 4.5, hexv
    assert colors.pick_brand([{"hex": "#111111", "share": 0.6}, {"hex": "#fafafa", "share": 0.4}]) is None
    assert colors.pick_brand([{"hex": "#111111", "share": 0.6}, {"hex": "#d62828", "share": 0.2}]) == "#d62828"


def test_type_mood_follows_industry():
    assert moods.from_industry("Food distribution") == "works"  # distribution outranks food on a tie
    assert moods.from_industry("Restaurant and catering") == "market"
    assert moods.from_industry("Dental clinic") == "care"
    assert moods.from_industry("Digital marketing agency") == "studio"
    assert moods.from_industry("Accounting firm") == "report"
    assert moods.from_industry(None) == moods.from_industry("Something else") == "report"


# ---- API ---------------------------------------------------------------------------------------------------------

def test_defaults_follow_the_platform_and_the_industry(owner):
    owner.patch("/api/v1/company/profile", json={"industry": "Restaurant and catering"})
    b = owner.get("/api/v1/org/branding").json()
    assert b["logo_url"] is None and b["accent"]["source"] == "platform"
    assert (b["mood"]["key"], b["mood_source"]) == ("market", "industry")
    assert {m["key"] for m in b["moods"]} == set(moods.MOODS)
    assert b["accent"]["contrast"]["light_on_ground"] >= 4.5


def test_logo_upload_derives_an_accessible_accent_and_is_re_encoded(owner):
    owner.patch("/api/v1/company/profile", json={"industry": "Food distribution"})
    r = upload(owner, png(extra=b"<script>alert(1)</script>"))
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["accent"]["source"] == "logo" and b["logo_brand"] is not None
    assert colors.hls(b["logo_brand"])[0] == pytest.approx(colors.hls("#f5c400")[0], abs=0.03)
    c = b["accent"]["contrast"]
    assert c["light_on_ground"] >= 4.5 and c["text_on_light"] >= 4.5 and c["dark_on_ground"] >= 4.5
    assert c["text_on_dark"] >= 4.5 and c["marker_on_rail"] >= 3.0
    assert b["accent"]["adjusted"], "the yellow had to be darkened and the change is explained"
    assert b["mood"]["key"] == "works"
    logo = owner.get(b["logo_url"])
    assert logo.status_code == 200 and logo.headers["content-type"] == "image/png"
    assert b"<script>" not in logo.content and logo.content.endswith(b"IEND\xaeB`\x82")  # pixels only
    assert max(b["logo_width"], b["logo_height"]) <= 512
    audit = owner.get("/api/v1/audit?action=branding.").json()
    assert audit[0]["action"] == "branding.logo_uploaded" and audit[0]["data"]["brand_colour"]
    # A monochrome logo has no brand colour: the platform accent is kept and the owner can pick one.
    b = upload(owner, png(fill="#202020")).json()
    assert b["logo_brand"] is None and b["accent"]["source"] == "platform"
    assert owner.put("/api/v1/org/branding", json={"accent_source": "logo"}).status_code == 409


def test_bad_logos_are_refused(owner):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    for data, name in ((svg, "logo.svg"), (b"GIF89a" + b"\x00" * 50, "logo.gif"), (b"not an image", "x.png"),
                       (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "broken.png"), (png(size=(4200, 40)), "wide.png"),
                       (b"\x89PNG\r\n\x1a\n" + b"\x00" * (1024 * 1024 + 10), "huge.png")):
        r = upload(owner, data, name)
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_logo", (name, r.text)
    assert upload(owner, png(fmt="JPEG"), "logo.jpg").status_code == 200


def test_overrides_permissions_and_tenancy(owner, rival, db):
    upload(owner, png(fill="#0047ab"))
    r = owner.put("/api/v1/org/branding", json={"accent_source": "owner", "owner_accent": "#FFD100",
                                                "mood": "studio"})
    b = r.json()
    assert r.status_code == 200 and b["accent"]["source"] == "owner" and b["accent"]["brand"] == "#ffd100"
    assert b["accent"]["contrast"]["light_on_ground"] >= 4.5 and (b["mood"]["key"], b["mood_source"]) == (
        "studio", "owner")
    assert owner.put("/api/v1/org/branding", json={"accent_source": "owner"}).status_code == 422
    assert owner.put("/api/v1/org/branding", json={"accent_source": "platform", "mood": "comic"}).status_code == 422
    assert owner.put("/api/v1/org/branding", json={"accent_source": "owner", "owner_accent": "red"}
                     ).status_code == 422
    viewer = join(owner, "viewer@acme.example.com", "viewer")
    assert viewer.get("/api/v1/org/branding").json()["accent"]["brand"] == "#ffd100"  # every member is themed
    assert viewer.get(b["logo_url"]).status_code == 200
    assert upload(viewer, png()).status_code == 403
    assert viewer.put("/api/v1/org/branding", json={"accent_source": "platform"}).status_code == 403
    assert viewer.delete("/api/v1/org/branding/logo").status_code == 403
    # The rival sees only its own (default) branding and can't fetch the owner's logo.
    assert rival.get("/api/v1/org/branding").json()["logo_url"] is None
    assert rival.client.get("/api/v1/org/branding/logo", headers={"X-Org-Id": owner.org_id}).status_code == 403
    assert rival.get("/api/v1/org/branding/logo").status_code == 404
    # The export carries the logo; removing it falls back to the platform accent unless a colour was picked.
    owner.post("/api/v1/org/exports")
    export = owner.get("/api/v1/org/exports").json()[0]
    z = zipfile.ZipFile(io.BytesIO(owner.get(f"/api/v1/org/exports/{export['id']}/download").content))
    assert "files/branding/logo.png" in z.namelist() and "tables/workspace_branding.json" in z.namelist()
    b = owner.delete("/api/v1/org/branding/logo").json()
    assert b["logo_url"] is None and b["accent"]["source"] == "owner"
    b = owner.put("/api/v1/org/branding", json={"accent_source": "platform", "mood": None}).json()
    assert b["accent"]["source"] == "platform" and b["mood_source"] == "industry"
