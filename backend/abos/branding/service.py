"""Workspace branding (ADR-035). Business logic only; the router authorises (org.read to view, org.manage to change).

The accent is always re-derived from its source on read, so a change to the platform's grounds or contrast rules
applies to every workspace without a migration; only the owner's inputs (logo, picked colour, mood) are stored.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.audit import service as audit
from abos.branding import colors, moods
from abos.branding.logo import process
from abos.branding.models import WorkspaceBranding
from abos.branding.schemas import AccentOut, BrandingIn, BrandingOut, MoodOut
from abos.company import service as company
from abos.core.errors import AppError, not_found
from abos.identity.deps import OrgContext
from abos.storage import branding_key, get_storage

log = logging.getLogger("abos.branding")


def _row(db: Session, org_id: uuid.UUID) -> WorkspaceBranding | None:
    return db.scalar(select(WorkspaceBranding).where(WorkspaceBranding.organization_id == org_id))


def _mood(key: str) -> MoodOut:
    m = moods.MOODS[key]
    return MoodOut(key=key, label=m["label"], display=m["display"], text=m["text"], description=m["for"])


def _accent(row: WorkspaceBranding | None) -> tuple[colors.Accent, str]:
    source = row.accent_source if row else "platform"
    brand = None
    if source == "owner" and row and row.owner_accent:
        brand = row.owner_accent
    elif source == "logo" and row:
        brand = colors.pick_brand(row.logo_palette or [])
    if brand is None:
        return colors.platform_accent(), "platform"
    return colors.derive(brand), source


def view(db: Session, org_id: uuid.UUID) -> BrandingOut:
    row = _row(db, org_id)
    accent, source = _accent(row)
    industry = company.get_profile(db, org_id).industry
    mood_key = row.mood if row and row.mood in moods.MOODS else moods.from_industry(industry)
    logo_brand = colors.pick_brand(row.logo_palette or []) if row and row.logo_key else None
    return BrandingOut(
        logo_url=f"/api/v1/org/branding/logo?v={row.logo_key.rsplit('/', 1)[-1][:8]}" if row and row.logo_key else None,
        logo_width=row.logo_width if row else None, logo_height=row.logo_height if row else None,
        palette=(row.logo_palette or []) if row and row.logo_key else [], logo_brand=logo_brand,
        accent=AccentOut(source=source, **{k: getattr(accent, k) for k in (
            "brand", "light", "on_light", "fill_light", "on_fill_light", "soft_light", "dark", "on_dark", "fill_dark",
            "on_fill_dark", "soft_dark", "marker", "note_light", "note_dark", "adjusted")},
            contrast={"light_on_ground": round(colors.contrast(accent.light, colors.LIGHT_TEXT_GROUND), 2),
                      "text_on_light": round(colors.contrast(accent.on_fill_light, accent.fill_light), 2),
                      "dark_on_ground": round(colors.contrast(accent.dark, colors.DARK_TEXT_GROUND), 2),
                      "text_on_dark": round(colors.contrast(accent.on_fill_dark, accent.fill_dark), 2),
                      "marker_on_rail": round(colors.contrast(accent.marker, colors.SHELL), 2)}),
        mood=_mood(mood_key), mood_source="owner" if row and row.mood else "industry", industry=industry,
        moods=[_mood(k) for k in moods.MOODS])


def _ensure(db: Session, ctx: OrgContext) -> WorkspaceBranding:
    row = _row(db, ctx.org_id)
    if row is None:
        row = WorkspaceBranding(organization_id=ctx.org_id, accent_source="platform", logo_palette=[])
        db.add(row)
    row.updated_by_id = ctx.user.id
    return row


def upload_logo(db: Session, ctx: OrgContext, data: bytes) -> BrandingOut:
    png, width, height, palette = process(data)
    key = branding_key(ctx.org_id, uuid.uuid4())
    get_storage().put(key, png, "image/png")
    row = _ensure(db, ctx)
    old = row.logo_key
    row.logo_key, row.logo_width, row.logo_height, row.logo_palette = key, width, height, palette
    brand = colors.pick_brand(palette)
    if row.accent_source != "owner":
        row.accent_source = "logo" if brand else "platform"
    audit.record(db, "branding.logo_uploaded", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="branding",
                 target_id=row.id, data={"brand_colour": brand, "width": width, "height": height}, ip=ctx.meta.ip)
    db.commit()
    if old:
        _discard(old)
    return view(db, ctx.org_id)


def remove_logo(db: Session, ctx: OrgContext) -> BrandingOut:
    row = _row(db, ctx.org_id)
    if row is None or not row.logo_key:
        raise not_found("Logo")
    old = row.logo_key
    row.logo_key = row.logo_width = row.logo_height = None
    row.logo_palette = []
    if row.accent_source == "logo":
        row.accent_source = "platform"
    row.updated_by_id = ctx.user.id
    audit.record(db, "branding.logo_removed", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="branding",
                 target_id=row.id, ip=ctx.meta.ip)
    db.commit()
    _discard(old)
    return view(db, ctx.org_id)


def update(db: Session, ctx: OrgContext, data: BrandingIn) -> BrandingOut:
    if data.mood is not None and data.mood not in moods.MOODS:
        raise AppError(422, "invalid_mood", f"Unknown type mood {data.mood!r}")
    if data.accent_source == "owner" and not data.owner_accent:
        raise AppError(422, "accent_required", "Pick a colour for a custom accent")
    row = _ensure(db, ctx)
    if data.accent_source == "logo" and not colors.pick_brand(row.logo_palette or []):
        raise AppError(409, "no_logo_colour", "Upload a logo with a distinct colour first, or pick a colour")
    before = {"accent_source": row.accent_source, "owner_accent": row.owner_accent, "mood": row.mood}
    row.accent_source = data.accent_source
    row.owner_accent = data.owner_accent if data.accent_source == "owner" else None
    row.mood = data.mood
    audit.record(db, "branding.updated", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="branding",
                 target_id=row.id, data={"from": before, "to": data.model_dump()}, ip=ctx.meta.ip)
    db.commit()
    return view(db, ctx.org_id)


def logo(db: Session, org_id: uuid.UUID) -> bytes:
    row = _row(db, org_id)
    if row is None or not row.logo_key:
        raise not_found("Logo")
    return get_storage().get(row.logo_key)


def _discard(key: str) -> None:
    try:
        get_storage().delete(key)
    except Exception as exc:  # noqa: BLE001 — the replaced file is unreferenced; leaving it costs storage, not safety
        log.warning("branding_logo_delete_failed", extra={"fields": {"error": type(exc).__name__}})
