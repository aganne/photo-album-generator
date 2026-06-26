"""Benchmark du scoring IA — identifie le goulet d'étranglement (v3)."""
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from album_generator.scoring import PhotoScorer, SCORE_WEIGHTS

PHOTOS_DIR = Path("/root/hermes-webui/public/mael_2012_photos/")
photos = sorted(list(PHOTOS_DIR.glob("*.JPG")) + list(PHOTOS_DIR.glob("*.jpg")))[:5]
print(f"Test sur {len(photos)} photos\n")

# Hook timing
original_score = PhotoScorer.score
def timed_score(self, image_path):
    import cv2
    import numpy as np
    t0 = time.time()

    path = Path(image_path)

    # --- Étape 0: Lecture ---
    t_pre = time.time()
    img_full = cv2.imread(str(path))
    if img_full is None:
        raise FileNotFoundError(f"Impossible de lire l'image : {image_path}")

    # --- Étape 0b: Downscale + cvtColor ---
    img_small, scale = self._downscale(img_full, self._ANALYSIS_MAX_DIM)
    gray_small = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)
    t_read = time.time()

    # --- Étape 1: Netteté ---
    sharpness_raw = self._sharpness(gray_small)
    sharpness = self._norm_sharpness(sharpness_raw / max(scale ** 2, 1e-6))
    t_sharp = time.time()

    # --- Étape 2: Exposition + Contraste ---
    exposure = self._exposure(img_small)
    contrast = self._norm_contrast(self._contrast(gray_small))
    t_exp = time.time()

    # --- Étape 3: Noise quality (local variance) ---
    noise_quality = self._noise_quality(img_small)
    t_noise = time.time()

    # --- Étape 4: Détection visages ---
    faces, landmarks = self._detect_all(img_full)
    t_faces = time.time()

    # --- Étape 5: Expressions ---
    smile = self._smile_score(landmarks, img_full.shape)
    t_smile = time.time()
    eyes = self._eyes_open_score(landmarks, img_full.shape)
    t_eyes = time.time()

    # --- Étape 6: Composition ---
    composition = self._composition(img_full, gray_small, img_small, faces)
    t_comp = time.time()

    # --- Score composite ---
    scores = {
        "sharpness": sharpness, "exposure": exposure,
        "contrast": contrast, "noise": noise_quality,
        "smile": smile, "eyes_open": eyes,
        "faces_count": min(len(faces), 4) / 4.0,
        "composition": composition,
    }
    total = sum(scores[k] * SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS)
    edge_penalty = self._face_edge_penalty(img_full, faces)
    total *= edge_penalty
    with PhotoScorer._face_cache_lock:
        PhotoScorer._face_cache[str(path)] = (list(faces), img_full.shape)
    total = max(0.0, min(1.0, total))

    t_total = time.time() - t0
    img_h, img_w = img_full.shape[:2]
    s_h, s_w = img_small.shape[:2]

    print(f"📷 {path.name} ({img_w}x{img_h} → {s_w}x{s_h}) — score={total:.3f} (pénalité={edge_penalty:.1f})")
    print(f"   imread+downscale: {t_read - t_pre:.3f}s")
    print(f"   sharpness       : {t_sharp - t_read:.3f}s")
    print(f"   exposure+cntrst : {t_exp - t_sharp:.3f}s")
    print(f"   Noise quality   : {t_noise - t_exp:.3f}s")
    print(f"   detect_all      : {t_faces - t_noise:.3f}s")
    print(f"   smile+eyes      : {t_eyes - t_faces:.3f}s")
    print(f"   composition     : {t_comp - t_eyes:.3f}s")
    print(f"   TOTAL           : {t_total:.3f}s")
    print(f"   faces détectés  : {len(faces)}")
    print()

    return total, scores

PhotoScorer.score = timed_score

print("=== BENCHMARK IA SCORING v3 ===\n")
print("Initialisation du scorer...")
t0 = time.time()
scorer = PhotoScorer()
print(f"Init scorer: {time.time() - t0:.2f}s\n")

for i, fp in enumerate(photos):
    try:
        scorer.score(str(fp))
    except Exception as exc:
        print(f"   ⚠️  Erreur pour {fp.name}: {exc}\n")
