import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandingIn(BaseModel):
    """Full replacement of the owner's choices. mood=None follows the company's industry."""

    model_config = ConfigDict(extra="forbid")

    accent_source: Literal["platform", "logo", "owner"]
    owner_accent: str | None = None
    mood: str | None = None

    @field_validator("owner_accent")
    @classmethod
    def _hex(cls, v: str | None) -> str | None:
        if v is not None and not HEX.match(v):
            raise ValueError("Use a #rrggbb colour")
        return v.lower() if v else v


class AccentOut(BaseModel):
    source: str
    brand: str
    light: str
    on_light: str
    fill_light: str
    on_fill_light: str
    soft_light: str
    dark: str
    on_dark: str
    fill_dark: str
    on_fill_dark: str
    soft_dark: str
    marker: str
    note_light: str
    note_dark: str
    adjusted: list[str]
    contrast: dict[str, float]


class MoodOut(BaseModel):
    key: str
    label: str
    display: str
    text: str
    description: str


class BrandingOut(BaseModel):
    logo_url: str | None
    logo_width: int | None
    logo_height: int | None
    palette: list[dict]
    logo_brand: str | None          # the colour picked from the logo, if it has one
    accent: AccentOut
    mood: MoodOut
    mood_source: Literal["industry", "owner"]
    industry: str | None
    moods: list[MoodOut]
