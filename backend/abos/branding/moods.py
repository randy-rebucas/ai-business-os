"""Type moods: curated display/text pairings a workspace can wear, matched from the company's industry. The frontend
holds the font files (frontend/src/lib/fonts.ts); keys here and there must match."""

MOODS: dict[str, dict] = {
    "report": {"label": "Report", "display": "Schibsted Grotesk", "text": "Public Sans",
               "for": "Professional services, finance, legal, real estate — the platform's own voice",
               "keywords": ("account", "financ", "legal", "law", "consult", "insur", "real estate", "property",
                            "bank", "audit", "tax", "professional")},
    "market": {"label": "Market", "display": "Bricolage Grotesque", "text": "Figtree",
               "for": "Retail, food service, hospitality, consumer brands",
               "keywords": ("retail", "restaurant", "food", "cafe", "café", "bakery", "grocer", "hospitality",
                            "hotel", "resort", "fashion", "beauty", "salon", "travel", "consumer", "store", "shop")},
    "works": {"label": "Works", "display": "Archivo", "text": "Archivo",
              "for": "Manufacturing, distribution, logistics, construction, agriculture",
              "keywords": ("manufactur", "distribut", "logistic", "wholesale", "construct", "agri", "farm",
                           "transport", "shipping", "trading", "engineer", "industrial", "supply", "warehouse")},
    "care": {"label": "Care", "display": "Source Serif 4", "text": "Source Sans 3",
             "for": "Health, clinics, education, non-profits",
             "keywords": ("health", "clinic", "medical", "dental", "pharma", "hospital", "school", "education",
                          "training", "nonprofit", "non-profit", "ngo", "foundation", "wellness", "care")},
    "studio": {"label": "Studio", "display": "Familjen Grotesk", "text": "Hanken Grotesk",
               "for": "Marketing, media, creative and technology companies",
               "keywords": ("marketing", "media", "creative", "design", "agency", "software", "technology",
                            "tech", "digital", "studio", "advertis", "film", "music", " it ")},
}
DEFAULT = "report"
_TIE_ORDER = ("care", "works", "market", "studio", "report")


def from_industry(industry: str | None) -> str:
    """The mood whose keywords match the industry most often (ties broken by `_TIE_ORDER`); the platform's own voice
    when nothing matches."""
    text = f" {(industry or '').lower()} "
    scores = {key: sum(1 for k in mood["keywords"] if k in text) for key, mood in MOODS.items()}
    best = max(scores.values())
    if best == 0:
        return DEFAULT
    return next(k for k in _TIE_ORDER if scores[k] == best)
