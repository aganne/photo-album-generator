#!/usr/bin/env python3
"""Quick validation of V2 templates P1-P7."""
import sys
sys.path.insert(0, '/root/photo-album-generator')

from album_generator.templates import (
    get_all_templates, get_template_by_id, TemplateSelector,
    PhotoDispatcher, TextGenerator,
)

print("=== Template V2 Validation ===")

# 1. Load
templates = get_all_templates()
ids = [t.id for t in templates]
print(f"Loaded {len(templates)} templates: {ids}")

# 2. No T1-T8
for tid in ['T1','T2','T3','T4','T5','T6','T7','T8']:
    assert get_template_by_id(tid) is None, f"{tid} still exists!"
print("  OK: no T1-T8 remains")

# 3. P1-P7 + T9 all valid
for tid in ['P1','P2','P3','P4','P5','P6','P7','T9']:
    t = get_template_by_id(tid)
    assert t is not None, f"{tid} missing!"
    ok = t.validate()
    assert ok, f"{tid} has overlapping zones!"
print("  OK: all 8 templates valid (no overlaps)")

# 4. Details
for tid in ['P1','P2','P3','P4','P5','P6','P7','T9']:
    t = get_template_by_id(tid)
    print(f"  {tid}: {t.photo_zones}p/{t.text_zones}t, hero_min={t.hero_min_score():.2f}, name={t.name}")

# 5. Selector
selector = TemplateSelector()
assert 'T9' not in selector._AUTO_TEMPLATES
assert len(selector._AUTO_TEMPLATES) == 6
print(f"Auto templates: {selector._AUTO_TEMPLATES}")

# 6. Selection + dispatch
fake = [(f"/t/p{i}.jpg", s, {}) for i, s in enumerate([0.85,0.70,0.60,0.50,0.40], 1)]
sel = selector.select(fake, used_templates=[])
assert sel is not None, "No template selected!"
print(f"Selected for 5 photos (top=0.85): {sel.id}")

d = PhotoDispatcher(sel)
a = d.dispatch(fake)
tg = TextGenerator()
a = tg.generate_texts(a, fake)
for zid, z in a.items():
    pp = z.get('photo_path', '')
    txt = z.get('rendered_text', '')
    print(f"  {zid}: type={z['type']}, photo={'YES' if pp else 'no'}, text={repr(txt) if txt else ''}")

print("\nALL CHECKS PASSED")
