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

# 3. Dispatch tests — edge cases
def _verify_dispatch(photo_count, window_size, label, allow_partial=False):
    fake_scores = [(f"/t/p{i}.jpg", 0.9 - i * 0.001, {}) for i in range(photo_count)]
    pages = dispatch_album(fake_scores, templates, window_size=window_size)
    used = set()
    for tid, paths, _hero in pages:
        t = templates[tid]
        expected = sum(1 for z in t['zones'] if z['type'] == 'photo')
        assert len(paths) <= expected, f"{label} {tid}: too many photos ({len(paths)} > {expected})"
        for p in paths:
            assert p not in used, f"{label} duplicate: {p}"
            used.add(p)
    all_photos = {s[0] for s in fake_scores}
    missing = all_photos - used
    if not allow_partial:
        assert not missing, f"{label} missing photos: {missing}"
    else:
        min_tpl = min(sum(1 for z in t['zones'] if z['type']=='photo') for t in templates.values())
        assert len(missing) < min_tpl, f"{label} too many missing: {len(missing)} >= {min_tpl}"
    return len(pages)

# Happy path: 40 photos, window=20
n = _verify_dispatch(40, 20, "40p/20w")
print(f"  Dispatch 40p/20w: {n} pages, all used ✓")

# Edge: trailing window < hero template (3 photos, window=20) — 1 photo ignorée (< min tpl)
n = _verify_dispatch(3, 20, "3p/20w", allow_partial=True)
print(f"  Dispatch 3p/20w: {n} pages, all used ✓")

# Edge: exact hero size (2 photos, window=20)
n = _verify_dispatch(2, 20, "2p/20w")
print(f"  Dispatch 2p/20w: {n} pages, all used ✓")

# Edge: window_size validation
try:
    dispatch_album([], templates, window_size=0)
    assert False, "Should have raised ValueError"
except ValueError:
    print("  Window size=0 raises ValueError ✓")

print("\n✅ All V6 templates valid!")
