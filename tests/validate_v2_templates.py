#!/usr/bin/env python3
"""Quick validation of V6 templates N1-N12."""
import sys
sys.path.insert(0, '/root/photo-album-generator')

from album_generator.templates import load_templates, HERO_IDS, REGULAR_IDS, MAX_PER_WINDOW

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

# 2. IDs réservés
for hid in HERO_IDS:
    assert hid in templates, f"Hero template {hid} missing!"
print(f"  Heroes: {HERO_IDS}")

# 3. Templates réguliers
for rid in REGULAR_IDS:
    assert rid in templates, f"Regular template {rid} missing!"
print(f"  Regular: {REGULAR_IDS}")

# 4. Max per window
for tid, limit in MAX_PER_WINDOW.items():
    assert tid in templates, f"Limited template {tid} missing!"
print(f"  Max/window: {MAX_PER_WINDOW}")

# 5. Dispatch test
from album_generator.templates import dispatch_album
fake_scores = [(f"/t/p{i}.jpg", 0.9 - i * 0.05, {}) for i in range(40)]
pages = dispatch_album(fake_scores, templates, window_size=20)
print(f"  Dispatch test: {len(pages)} pages from 40 photos (window=20)")

print("\n✅ All V6 templates valid!")
