"""Smoke test pour vérifier que tous les points d'intégration tag_engine sont OK."""
import os
import sys
from pathlib import Path

# Ajouter le projet au path
PROJECT_DIR = Path(__file__).parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from album_generator.tag_engine import (
    apply_tags, get_effective_date, is_hero_tagged,
    get_score_boost, get_legend, count_tagged_photos,
)
from album_generator import apply_tags as api_apply_tags
print('✅ Imports OK')

# Vérification que l'API exportée depuis __init__ fonctionne
assert apply_tags is api_apply_tags, 'API mismatch'
print('✅ API exportée OK')

# Vérification que sort_by_exif_date accepte bien tag_context
from album_generator.scoring import sort_by_exif_date
import inspect
sig = inspect.signature(sort_by_exif_date)
assert 'tag_context' in sig.parameters, 'tag_context manquant dans sort_by_exif_date'
print('✅ sort_by_exif_date(tag_context=...) OK')

# Vérification que dispatch_album accepte tag_context
from album_generator.templates import dispatch_album
sig = inspect.signature(dispatch_album)
assert 'tag_context' in sig.parameters, 'tag_context manquant dans dispatch_album'
print('✅ dispatch_album(tag_context=...) OK')

# Vérification que arrange_pages_from_scores_v3 accepte tag_context
from generate import arrange_pages_from_scores_v3
sig = inspect.signature(arrange_pages_from_scores_v3)
assert 'tag_context' in sig.parameters, 'tag_context manquant dans arrange_pages_from_scores_v3'
print('✅ arrange_pages_from_scores_v3(tag_context=...) OK')

print()
print('=== Tous les points d intégration sont OK ===')
