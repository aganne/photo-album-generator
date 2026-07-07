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
from .colors import extract_palette, generate_dynamic_css, apply_palette_to_html
from .enhance import auto_enhance, batch_enhance, auto_enhance_file, ENHANCE_PARAMS
from .print_risk import compute_print_penalty, compute_print_penalty_file
from .tag_manager import (
    read_tags,
    write_tags,
    add_tag,
    remove_tag,
    clear_all_tags,
    list_all_tags,
)
from .tag_engine import (
    apply_tags,
    get_effective_date,
    is_hero_tagged,
    get_score_boost,
    get_legend,
    count_tagged_photos,
)
