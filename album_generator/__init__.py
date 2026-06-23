"""Générateur d'album photo PDF — Template Jinja2 → HTML → WeasyPrint."""

from .config import (
    PALETTE, FONTS, ALBUM, PAGE_STYLES,
    PAGE_WIDTH_MM, PAGE_HEIGHT_MM, BLEED_MM, SAFE_MARGIN_MM,
)
from .scoring import (
    PhotoScorer,
    PhotoDispatcher,
    extract_exif_date,
    sort_by_exif_date,
    group_photos_by_exif_month,
    export_scoring_report,
    find_micro_events,
    SCORE_WEIGHTS,
)
