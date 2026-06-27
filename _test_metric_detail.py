#!/usr/bin/env python3
"""Analyse métrique par métrique avant/après retouche"""
import sys
sys.path.insert(0, '/root/photo-album-generator')

import cv2
import numpy as np
from pathlib import Path
from album_generator.enhance import auto_enhance
from album_generator.scoring import PhotoScorer

PHOTOS_DIR = Path("/root/video_best_frames/best_photos/20230805_123206000_iOS")
test_photos = sorted(list(PHOTOS_DIR.glob("*.jpg")))[:3]

scorer = PhotoScorer()

for fp in test_photos:
    orig = cv2.imread(str(fp))
    enhanced = auto_enhance(orig, level="default")

    total_o, det_o = scorer.score(str(fp))

    # Sauvegarder enhanced dans tmp pour scoring
    import tempfile
    tmpdir = Path(tempfile.mkdtemp())
    enh_path = tmpdir / fp.name
    cv2.imwrite(str(enh_path), enhanced)
    total_e, det_e = scorer.score(str(enh_path))

    print(f"\n{'='*60}")
    print(f"📸 {fp.name}")
    print(f"{'Metric':<18} {'Avant':>8} {'Après':>8} {'Δ':>8}")
    print("-" * 42)
    for key in sorted(det_o.keys()):
        vo = det_o.get(key, 0.0)
        ve = det_e.get(key, 0.0)
        delta = ve - vo
        marker = "✓" if delta > 0.001 else ("✗" if delta < -0.001 else " ")
        print(f"{key:<18} {vo:>8.4f} {ve:>8.4f} {delta:>+8.4f} {marker}")

    # Calculer les scores techniques seulement
    tech_weights = {"sharpness": 0.20, "exposure": 0.10, "contrast": 0.05, "noise": 0.05}
    tech_before = sum(det_o.get(k, 0) * w for k,w in tech_weights.items())
    tech_after = sum(det_e.get(k, 0) * w for k,w in tech_weights.items())
    print(f"{'TECHNIQUE (0.40)':<18} {tech_before:>8.4f} {tech_after:>8.4f} {tech_after-tech_before:>+8.4f}")

    # Nettoyer
    import shutil
    shutil.rmtree(tmpdir)
