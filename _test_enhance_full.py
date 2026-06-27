#!/usr/bin/env python3
"""
Test complet pipeline --enhance + print_risk sur 5 photos.
Affiche : nom | score_avant | score_après | print_risk | dispatch
"""
import sys, os, tempfile
sys.path.insert(0, '/root/photo-album-generator')

import cv2
import numpy as np
from pathlib import Path

from album_generator.enhance import auto_enhance, ENHANCE_PARAMS
from album_generator.print_risk import compute_print_penalty
from album_generator.scoring import PhotoScorer

# ── Photos test ──
PHOTOS_DIR = Path("/root/video_best_frames/best_photos/20230805_123206000_iOS")
test_photos = sorted(list(PHOTOS_DIR.glob("*.jpg")))[:5]
TMP_DIR = Path(tempfile.mkdtemp(prefix="enhance_test_"))

print("=" * 80)
print("🧪 TEST PIPELINE --enhance + print_risk")
print(f"📸 {len(test_photos)} photos — tmp: {TMP_DIR}")
print("=" * 80)

# Init scorer
print("⚙️  Initialisation PhotoScorer...", flush=True)
scorer = PhotoScorer()
print("   ✓ Scorer prêt\n")

# ── Phase 1 : Scores avant ──
print("📊 Phase 1 : Scoring AVANT retouche...")
scores_avant = []
for i, fp in enumerate(test_photos):
    total, details = scorer.score(str(fp))
    scores_avant.append((str(fp), total, details))
    print(f"   [{i+1}/{len(test_photos)}] {fp.name:<45} score={total:.4f}")

# ── Phase 2 : Retouche + sauvegarde ──
print(f"\n🖼️  Phase 2 : Retouche (default)...")
enhanced_paths = {}
for i, fp in enumerate(test_photos):
    img = cv2.imread(str(fp))
    if img is None:
        print(f"   ❌ {fp.name} : échec lecture")
        continue
    enhanced = auto_enhance(img, level="default")
    out_path = TMP_DIR / fp.name
    cv2.imwrite(str(out_path), enhanced)
    enhanced_paths[str(fp)] = str(out_path)
    print(f"   [{i+1}/{len(test_photos)}] {fp.name} → {out_path.name}")

# ── Phase 3 : Scores après + Print Risk ──
print(f"\n📊 Phase 3 : Scoring APRÈS + print_risk...")
scores_apres = []
for i, fp in enumerate(test_photos):
    orig_path = str(fp)
    enh_path = enhanced_paths.get(orig_path)
    if enh_path is None:
        scores_apres.append((orig_path, scores_avant[i][1], scores_avant[i][2], 0.0, 0.0))
        continue

    # Score après retouche
    total_e, details_e = scorer.score(enh_path)

    # Print risk
    orig_img = cv2.imread(str(fp))
    enh_img = cv2.imread(enh_path)
    penalty = compute_print_penalty(orig_img, enh_img) if orig_img is not None and enh_img is not None else 0.0
    adjusted = total_e * (1.0 - penalty)

    scores_apres.append((enh_path, adjusted, details_e, total_e, penalty))
    print(f"   [{i+1}/{len(test_photos)}] {fp.name:<45} raw={total_e:.4f} penalty={penalty:.4f} adjusted={adjusted:.4f}")

# ── Affichage final ──
print(f"\n{'='*100}")
print(f"{'Photo':<48} {'Avant':>7} {'Après':>7} {'Δ':>7} {'Risk':>7}")
print("-" * 100)

def rank_str(scores_list, path, idx):
    """Trouve le rang dans la liste triée."""
    sorted_list = sorted(enumerate(scores_list), key=lambda x: x[1][1], reverse=True)
    for rank, (orig_idx, _) in enumerate(sorted_list):
        if orig_idx == idx:
            if rank == 0:
                return "🌟Héroïque"
            elif rank <= 3:
                return "📷Quatuor"
            else:
                return "🖼️Grille"
    return "?"

for i, fp in enumerate(test_photos):
    fname = fp.name[:46]
    score_before = scores_avant[i][1]
    score_after = scores_apres[i][1]
    penalty = scores_apres[i][4]
    delta = score_after - score_before

    print(f"{fname:<48} {score_before:>7.4f} {score_after:>7.4f} {delta:>+7.4f} {penalty:>7.4f}")

# ── Résumé ──
print(f"\n{'='*100}")
print("📊 RÉSUMÉ")
before_vals = [s[1] for s in scores_avant]
after_vals = [s[1] for s in scores_apres]
penalties = [s[4] for s in scores_apres]

print(f"   Score moyen avant  : {np.mean(before_vals):.4f}")
print(f"   Score moyen après  : {np.mean(after_vals):.4f}")
print(f"   Gain moyen         : {np.mean(after_vals) - np.mean(before_vals):+.4f}")
print(f"   Print risk moyen   : {np.mean(penalties):.4f} (max 0.30)")
print(f"   Score min→max avant: {min(before_vals):.4f} → {max(before_vals):.4f}")
print(f"   Score min→max après: {min(after_vals):.4f} → {max(after_vals):.4f}")

# Nettoyage
import shutil
shutil.rmtree(TMP_DIR, ignore_errors=True)

print("\n✨ Test terminé !")
