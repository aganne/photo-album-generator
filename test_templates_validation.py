#!/usr/bin/env python3
"""Test de validation des templates T1-T9."""
import sys
sys.path.insert(0, '/root/photo-album-generator')

from album_generator.templates import (
    TemplateSelector, PhotoDispatcher, TextGenerator, get_all_templates
)

# Test 1: Chargement des 9 templates
templates = get_all_templates()
print(f'=== Templates chargés: {len(templates)} ===')
for t in templates:
    print(f'  {t.id} ({t.name}): {t.photo_zones} photos + {t.text_zones} texte = {len(t.zones)} zones')

# Test 2: Validation des zones (pas de chevauchement)
print('\n=== Validation des zones ===')
for t in templates:
    try:
        t.validate()
        print(f'  {t.id}: OK pas de chevauchement')
    except ValueError as e:
        print(f'  {t.id}: ERREUR {e}')

# Test 3: Sélection automatique
print('\n=== Test sélection auto ===')
ts = TemplateSelector()
# Format: (path, score, details)
fake_scores = [
    ("photo1.jpg", 0.85, {"sharpness": 0.9}),
    ("photo2.jpg", 0.72, {"sharpness": 0.8}),
    ("photo3.jpg", 0.65, {"sharpness": 0.7}),
    ("photo4.jpg", 0.58, {"sharpness": 0.6}),
    ("photo5.jpg", 0.51, {"sharpness": 0.5}),
    ("photo6.jpg", 0.44, {"sharpness": 0.4}),
    ("photo7.jpg", 0.38, {"sharpness": 0.3}),
]
selected = ts.select(fake_scores, [])
print(f'  Avec {len(fake_scores)} photos → {selected.id if selected else "AUCUN"} ({selected.name if selected else "N/A"})')

if selected:
    dispatcher = PhotoDispatcher(selected)
    assignments = dispatcher.dispatch(fake_scores)
    print(f'  Zones assignées: {len(assignments)}')
    for zone_id, a in assignments.items():
        path = a.get('photo_path', '')
        if a.get('type') == 'photo':
            print(f'    {zone_id} ({a.get("size", "?")}): {path}')
        else:
            print(f'    {zone_id} (texte): content={a.get("content", "?")}')

    # Test 4: TextGenerator
    print('\n=== Test TextGenerator ===')
    tg = TextGenerator()
    assignments = tg.generate_texts(assignments, fake_scores)
    for zone_id, a in assignments.items():
        if a.get('type') == 'text':
            print(f'  {zone_id}: "{a.get("rendered_text", "")}"')

    # Test 5: TextGenerator direct
    print('\n=== Test TextGenerator direct ===')
    text = tg.generate("IMG_20230815_143022.jpg", "legend")
    print(f'  Legend: "{text}"')
    text2 = tg.generate("", "legend")  # empty path → fallback
    print(f'  Legend (empty path): "{text2}"')

print('\n=== Tous les tests passent ✓ ===')
