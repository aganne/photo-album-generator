#!/usr/bin/env python3
"""Quick validation of V6 templates N1-N12."""
import sys
from pathlib import Path

# Portable: derive repo root from __file__
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from album_generator.templates import load_templates, dispatch_album, _derive_ids

templates = load_templates()
ids = sorted(templates.keys())
print(f"Loaded {len(templates)} templates: {ids}")

# 1. Tous les templates sont valides
for tid in ids:
    t = templates[tid]
    assert 'grid' in t, f"{tid}: missing grid"
    assert 'zones' in t, f"{tid}: missing zones"
    n_photos = sum(1 for z in t['zones'] if z['type'] == 'photo')
    assert n_photos > 0, f"{tid}: no photo zones"
    print(f"  {tid}: {n_photos}p / {t['grid']['cols']}x{t['grid']['rows']} — {t['name']}")

# 2. IDs dérivés depuis le JSON (source unique)
hero_ids, max_per_window, regular_ids = _derive_ids(templates)
print(f"  Heroes (from JSON): {hero_ids}")
print(f"  Max/window (from JSON): {max_per_window}")
print(f"  Regular (from JSON): {regular_ids}")

# 3. Dispatch test — vérifie que toutes les photos sont consommées
fake_scores = [(f"/t/p{i}.jpg", 0.9 - i * 0.01, {}) for i in range(40)]
pages = dispatch_album(fake_scores, templates, window_size=20)

# Vérifier que chaque photo est utilisée exactement une fois
used = set()
for tid, paths, _hero in pages:
    t = templates[tid]
    expected = sum(1 for z in t['zones'] if z['type'] == 'photo')
    assert len(paths) <= expected, f"{tid}: too many photos ({len(paths)} > {expected})"
    for p in paths:
        assert p not in used, f"Duplicate photo: {p}"
        used.add(p)

all_photos = {s[0] for s in fake_scores}
missing = all_photos - used
assert not missing, f"Missing photos: {missing}"

print(f"  Dispatch: {len(pages)} pages, all {len(all_photos)} photos used ✓")

print("\n✅ All V6 templates valid!")
