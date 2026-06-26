"""
Moteur IA de scoring photo — évalue la qualité technique, le contenu et la
composition pour dispatcher les photos dans les spreads de l'album.

Stack : OpenCV (netteté, exposition, contraste) + MediaPipe (visages, sourires,
yeux) + variance locale (bruit). CPU only, ~0.4s/photo.

Usage :
    scorer = PhotoScorer()
    dispatcher = PhotoDispatcher()
    results = [(path, *scorer.score(path)) for path in photo_paths]
    dispatch = dispatcher.dispatch(results)
"""

from __future__ import annotations

import json
import math
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import mediapipe as mp
import numpy as np
import threading
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# ── Cache des modèles MediaPipe ──────────────────────────────────────

_MODEL_CACHE_DIR = Path.home() / ".cache" / "mediapipe_models"
_MODEL_URLS = {
    "face_detector": "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
    "face_landmarker": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
}


def _ensure_model(model_name: str) -> str:
    """Télécharge et met en cache un modèle MediaPipe au premier usage."""
    _MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = _MODEL_URLS[model_name]
    ext = ".task" if model_name == "face_landmarker" else ".tflite"
    local_path = _MODEL_CACHE_DIR / f"{model_name}{ext}"

    if not local_path.exists():
        print(f"   ⬇️  Téléchargement du modèle {model_name}...")
        import tempfile
        tmp = tempfile.NamedTemporaryFile(dir=_MODEL_CACHE_DIR, delete=False, suffix=ext)
        try:
            import urllib.request as ureq
            resp = ureq.urlopen(url, timeout=30)
            with open(tmp.name, 'wb') as f_tmp:
                f_tmp.write(resp.read())
            resp.close()
            tmp.close()
            os.replace(tmp.name, local_path)
        except Exception:
            tmp.close()
            os.unlink(tmp.name)
            raise

    return str(local_path)


# ── Poids du score composite final ────────────────────────────────────
# Définis d'après le rapport Athéna (complément dispatch 7/13/80)
SCORE_WEIGHTS: Dict[str, float] = {
    "smile":         0.25,  # Sourire = le plus important (émotion)
    "sharpness":     0.20,  # Netteté (photo floue = poubelle)
    "composition":   0.15,  # Règle des tiers, espace négatif
    "eyes_open":     0.10,  # Yeux ouverts (pas de clignement)
    "exposure":      0.10,  # Bonne exposition
    "faces_count":   0.10,  # Nombre de personnes
    "contrast":      0.05,  # Contraste global
    "noise":         0.05,  # Bruit faible
}


class PhotoScorer:
    """Score une photo sur 3 axes : technique, contenu, composition.

    Les modèles MediaPipe sont chargés une seule fois (coûteux à
    l'initialisation), puis réutilisés pour chaque photo.
    """

    # Cache global (classe) pour mutualiser les détections entre
    # le scoring et le smart_crop.  Format : path → (faces_list, img_shape)
    _face_cache: Dict[str, Tuple[List[Any], Tuple[int, int, int]]] = {}
    _face_cache_lock = threading.Lock()

    def __init__(self) -> None:
        # Modèles téléchargés au premier usage
        fd_model = _ensure_model("face_detector")
        fl_model = _ensure_model("face_landmarker")

        # Face detector (boîtes englobantes)
        fd_options = vision.FaceDetectorOptions(
            base_options=python.BaseOptions(model_asset_path=fd_model),
            running_mode=vision.RunningMode.IMAGE,
        )
        self._face_detector = vision.FaceDetector.create_from_options(fd_options)

        # Face landmarker (478 points)
        fl_options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=fl_model),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=6,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._face_landmarker = vision.FaceLandmarker.create_from_options(fl_options)

    # ── Taille max pour l'image d'analyse (gain ×20-30) ──
    _ANALYSIS_MAX_DIM = 1024

    def _downscale(self, img: np.ndarray, max_dim: int) -> Tuple[np.ndarray, float]:
        """Réduit l'image à max_dim px de côté max.

        Returns:
            (img_resized, scale) où scale = new_dim / old_dim.
        """
        h, w = img.shape[:2]
        max_src = max(h, w)
        if max_src <= max_dim:
            return img, 1.0
        scale = max_dim / max_src
        small = cv2.resize(img, (int(w * scale), int(h * scale)),
                           interpolation=cv2.INTER_AREA)
        return small, scale

    def score(self, image_path: str | Path) -> Tuple[float, Dict[str, float]]:
        """Calcule le score complet d'une photo.

        Returns:
            (total_score, details_dict) où total_score ∈ [0, 1] et
            details_dict contient chaque sous-score normalisé.
        """
        path = Path(image_path)
        img_full = cv2.imread(str(path))
        if img_full is None:
            raise FileNotFoundError(f"Impossible de lire l'image : {image_path}")

        # ── Image d'analyse réduite (1024px) ──
        # Toute la qualité technique tourne sur l'image réduite, sauf la
        # détection de visages (MediaPipe a besoin de la pleine résolution).
        img_small, scale = self._downscale(img_full, self._ANALYSIS_MAX_DIM)
        gray_small = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)

        # 1. Qualité technique (sur img_small)
        sharpness_raw = self._sharpness(gray_small)
        # La variance du Laplacian est ~ scale² fois plus petite sur l'image
        # réduite → on compense avant normalisation.
        sharpness = self._norm_sharpness(
            sharpness_raw / max(scale ** 2, 1e-6)
        )
        exposure = self._exposure(img_small)
        contrast = self._norm_contrast(self._contrast(gray_small))
        noise_quality = self._noise_quality(img_small)

        # 2. Détection de contenu (sur img_full — MediaPipe)
        faces, landmarks = self._detect_all(img_full)
        smile = self._smile_score(landmarks, img_full.shape)
        eyes = self._eyes_open_score(landmarks, img_full.shape)

        # 3. Composition : _rule_of_thirds sur full-res (coords visages),
        #    _negative_space et _saturation sur small.
        composition = self._composition(
            img_full, gray_small, img_small, faces,
        )

        # Normalisation et score composite
        scores: Dict[str, float] = {
            "sharpness":   sharpness,
            "exposure":    exposure,
            "contrast":    contrast,
            "noise":       noise_quality,
            "smile":       smile,
            "eyes_open":   eyes,
            "faces_count": min(len(faces), 4) / 4.0,
            "composition": composition,
        }

        total = sum(scores[k] * SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS)

        # ── Pénalité visage en bordure (sur img_full) ──
        edge_penalty = self._face_edge_penalty(img_full, faces)
        total *= edge_penalty

        # ── Cache pour smart_crop (thread-safe) ──
        with PhotoScorer._face_cache_lock:
            PhotoScorer._face_cache[str(path)] = (list(faces), img_full.shape)

        total = max(0.0, min(1.0, total))

        return total, scores

    # ── Qualité technique ──────────────────────────────────────────

    def _sharpness(self, gray: np.ndarray) -> float:
        """Variance du Laplacien — netteté perçue."""
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @staticmethod
    def _norm_sharpness(val: float, cap: float = 500.0) -> float:
        return min(val / cap, 1.0)

    @staticmethod
    def _exposure(img: np.ndarray) -> float:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        well_exposed = np.sum((gray >= 30) & (gray <= 250))
        return float(well_exposed / gray.size)

    @staticmethod
    def _contrast(gray: np.ndarray) -> float:
        return float(np.std(gray))

    @staticmethod
    def _norm_contrast(val: float, cap: float = 80.0) -> float:
        return min(val / cap, 1.0)
    # ── Taille max pour estimation du bruit (gain ×500 : 25s → 0.003s) ──
    _NOISE_MAX_DIM = 512

    @staticmethod
    def _noise_quality(img: np.ndarray) -> float:
        """Estime la qualité via le bruit local (remplace l'analyse de référence).

        Divise l'image en blocs de 16×16 px et calcule l'écart-type
        local.  Le 90ème percentile de ces écarts-types mesure le
        niveau de bruit — plus il est élevé, plus l'image est bruitée.

        L'image est réduite à 512 px de côté max avant analyse pour
        un coût ~3 ms au lieu des ~25 s de l'analyse classique.
        """
        try:
            # Réduire si nécessaire
            h, w = img.shape[:2]
            if max(h, w) > PhotoScorer._NOISE_MAX_DIM:
                scale = PhotoScorer._NOISE_MAX_DIM / max(h, w)
                small = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            else:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            block_size = 16
            n_blocks_h = h // block_size
            n_blocks_w = w // block_size
            if n_blocks_h < 2 or n_blocks_w < 2:
                return 0.5

            # Recadrer au multiple de block_size
            gray = gray[:n_blocks_h * block_size, :n_blocks_w * block_size]

            # Reshape → (N_blocks, block_size²)
            blocks = gray.reshape(
                n_blocks_h, block_size, n_blocks_w, block_size
            )
            blocks = blocks.transpose(0, 2, 1, 3)
            blocks = blocks.reshape(n_blocks_h * n_blocks_w,
                                    block_size * block_size)

            local_stds = np.std(blocks.astype(np.float64), axis=1)
            noise_level = float(np.percentile(local_stds, 90))

            # Normalisation : cap à 35 pour une bonne discrimination
            #   < 10 → très propre (Q > 0.71)
            #   ~18  → typique   (Q ≈ 0.49)
            #   > 35 → très bruité (Q = 0)
            quality = max(0.0, 1.0 - noise_level / 35.0)
            return float(quality)
        except Exception:
            return 0.5

    # ── Détection de contenu (API tasks) ──────────────────────────

    def _detect_all(self, img: np.ndarray,
                    max_dim: int = 1024) -> Tuple[List, Any]:
        """Détecte les visages et les landmarks via l'API tasks.

        L'image est réduite à max_dim px de côté max avant détection
        (gain ×3-5 sur CPU).  Les coordonnées retournées sont remises
        à l'échelle de l'image d'origine pour le smart crop.

        Optimisation : le face_landmarker n'est appelé que si au moins
        un visage est détecté (gain ~50-100 ms par photo sans visage).

        Returns:
            (faces, face_landmarks_result)
            faces: liste de Detection (boîtes englobantes, coordonnées
                   dans l'espace de l'image d'origine)
            landmarks: FaceLandmarkerResult ou None (coordonnées dans
                       l'espace de l'image d'origine)
        """
        h, w = img.shape[:2]
        max_src = max(h, w)
        if max_src > max_dim:
            scale = max_dim / max_src
            small = cv2.resize(img, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_AREA)
        else:
            scale = 1.0
            small = img

        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # Face detection (boîtes)
        fd_result = self._face_detector.detect(mp_image)
        faces = fd_result.detections if fd_result.detections else []

        # Face landmarks — uniquement si visages détectés
        if faces:
            fl_result = self._face_landmarker.detect(mp_image)
            landmarks = fl_result if fl_result.face_landmarks else None
        else:
            landmarks = None

        # Rescale les coordonnées dans l'espace de l'image d'origine
        if scale != 1.0:
            inv_scale = 1.0 / scale
            for det in faces:
                bbox = det.bounding_box
                bbox.origin_x = int(bbox.origin_x * inv_scale)
                bbox.origin_y = int(bbox.origin_y * inv_scale)
                bbox.width = int(bbox.width * inv_scale)
                bbox.height = int(bbox.height * inv_scale)
            # Les landmarks sont en coordonnées normalisées [0,1] par
            # MediaPipe, donc pas besoin de rescale.

        return faces, landmarks

    @staticmethod
    def _get_landmark_pt(landmark, w: int, h: int) -> np.ndarray:
        """Convertit un NormalizedLandmark en coordonnées pixel."""
        return np.array([landmark.x * w, landmark.y * h])

    def _smile_score(
        self, landmarks_result: Any, shape: Tuple[int, int, int]
    ) -> float:
        """Score de sourire basé sur le ratio d'ouverture de la bouche.

        Landmarks MediaPipe :
          13  : lèvre supérieure
          14  : lèvre inférieure
          61  : coin gauche de la bouche
          291 : coin droit de la bouche
        """
        if landmarks_result is None:
            return 0.0

        h, w = shape[:2]
        smiles = []

        for face_lm in landmarks_result.face_landmarks:
            upper = self._get_landmark_pt(face_lm[13], w, h)
            lower = self._get_landmark_pt(face_lm[14], w, h)
            left = self._get_landmark_pt(face_lm[61], w, h)
            right = self._get_landmark_pt(face_lm[291], w, h)

            mouth_h = float(np.linalg.norm(upper - lower))
            mouth_w = float(np.linalg.norm(left - right))

            if mouth_w > 1e-6:
                ratio = mouth_h / mouth_w
                smiles.append(min(ratio / 0.5, 1.0))

        return float(np.mean(smiles)) if smiles else 0.0

    def _eyes_open_score(
        self, landmarks_result: Any, shape: Tuple[int, int, int]
    ) -> float:
        """Score d'ouverture des yeux via EAR (Eye Aspect Ratio).

        Landmarks :
          Œil gauche  : 33(gauche), 159(haut), 145(bas), 133(droite)
          Œil droit   : 362(gauche), 386(haut), 374(bas), 263(droite)
        """
        if landmarks_result is None:
            return 0.0

        h, w = shape[:2]
        left_indices = [33, 159, 145, 133]
        right_indices = [362, 386, 374, 263]
        ears = []

        for face_lm in landmarks_result.face_landmarks:
            try:
                # EAR œil gauche
                pts = [self._get_landmark_pt(face_lm[i], w, h) for i in left_indices]
                v_dist = float(np.linalg.norm(pts[1] - pts[2]))
                h_dist = float(np.linalg.norm(pts[0] - pts[3]))
                ear_l = v_dist / h_dist if h_dist > 1e-6 else 0.0

                # EAR œil droit
                pts = [self._get_landmark_pt(face_lm[i], w, h) for i in right_indices]
                v_dist = float(np.linalg.norm(pts[1] - pts[2]))
                h_dist = float(np.linalg.norm(pts[0] - pts[3]))
                ear_r = v_dist / h_dist if h_dist > 1e-6 else 0.0

                avg = (ear_l + ear_r) / 2.0
                normalized = min(max((avg - 0.12) / 0.18, 0.0), 1.0)
                ears.append(normalized)
            except (IndexError, AttributeError):
                pass

        return float(np.mean(ears)) if ears else 0.0

    # ── Composition ────────────────────────────────────────────────

    def _composition(
        self, img_full: np.ndarray, gray_small: np.ndarray,
        img_small: np.ndarray, faces: List[Any],
    ) -> float:
        # _rule_of_thirds : utilise img_full si visages (coordonnées
        # précises), sinon img_small pour le Sobel fallback (×10 plus
        # rapide sur 1024px que sur 18MP).
        if faces:
            thirds = self._rule_of_thirds(img_full, faces)
        else:
            thirds = self._rule_of_thirds(img_small, faces)
        neg_space = self._negative_space(gray_small)
        saturation = self._saturation(img_small)
        return (thirds * 0.40) + (neg_space * 0.30) + (saturation * 0.30)

    def _rule_of_thirds(
        self, img: np.ndarray, faces: List[Any]
    ) -> float:
        h, w = img.shape[:2]
        if h < 10 or w < 10:
            return 0.5

        # Points de force (intersections 1/3 - 2/3)
        force_pts = [
            (w / 3, h / 3),
            (2 * w / 3, h / 3),
            (w / 3, 2 * h / 3),
            (2 * w / 3, 2 * h / 3),
        ]

        # Centres des visages (nouvelle API : bounding_box avec origin)
        interest_pts = []
        for det in faces:
            bbox = det.bounding_box
            cx = bbox.origin_x + bbox.width / 2
            cy = bbox.origin_y + bbox.height / 2
            interest_pts.append((cx, cy))

        if not interest_pts:
            # Fallback : centre de masse des gradients Sobel
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            magnitude = np.sqrt(sobel_x ** 2 + sobel_y ** 2)
            ys, xs = np.indices(magnitude.shape)
            total = magnitude.sum()
            if total > 0:
                cx = float((xs * magnitude).sum() / total)
                cy = float((ys * magnitude).sum() / total)
                interest_pts.append((cx, cy))
            else:
                return 0.5

        diag = math.sqrt(w ** 2 + h ** 2)
        scores = []
        for ix, iy in interest_pts:
            min_dist = min(
                math.sqrt((ix - fx) ** 2 + (iy - fy) ** 2)
                for fx, fy in force_pts
            )
            scores.append(max(0.0, 1.0 - (min_dist / (diag * 0.35))))

        return float(np.mean(scores)) if scores else 0.5

    @staticmethod
    def _negative_space(gray: np.ndarray, block_size: int = 32) -> float:
        h, w = gray.shape[:2]
        if h < block_size or w < block_size:
            return 0.5

        n_blocks_h = h // block_size
        n_blocks_w = w // block_size
        total_blocks = n_blocks_h * n_blocks_w
        if total_blocks == 0:
            return 0.5

        low_var_count = 0
        for i in range(n_blocks_h):
            for j in range(n_blocks_w):
                block = gray[
                    i * block_size:(i + 1) * block_size,
                    j * block_size:(j + 1) * block_size,
                ]
                if np.var(block.astype(np.float64)) < 100:
                    low_var_count += 1

        ratio = low_var_count / total_blocks
        if ratio < 0.4:
            return ratio / 0.4
        else:
            return max(0.0, 1.0 - (ratio - 0.4) / 0.6)

    @staticmethod
    def _saturation(img: np.ndarray) -> float:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        s_mean = float(np.mean(hsv[:, :, 1]))
        return min(s_mean / 128.0, 1.0)

    # ── Pénalité visage en bordure ──────────────────────────────

    @staticmethod
    def _face_edge_penalty(img: np.ndarray, faces: List[Any]) -> float:
        """Pénalise les photos où un visage est trop proche du bord.

        Si un visage est à moins de 5% du bord de l'image, la photo
        est pénalisée (×0.3).  Sans visage détecté, pas de pénalité.
        """
        if not faces:
            return 1.0

        h, w = img.shape[:2]
        margin_x = w * 0.05
        margin_y = h * 0.05

        for det in faces:
            bbox = det.bounding_box
            x1 = bbox.origin_x
            y1 = bbox.origin_y
            x2 = x1 + bbox.width
            y2 = y1 + bbox.height

            if x1 < margin_x or y1 < margin_y or x2 > (w - margin_x) or y2 > (h - margin_y):
                return 0.3  # pénalité forte

        return 1.0

    # ── Zone de sécurité visages (smart crop) ──────────────────────

    @staticmethod
    def face_safety_region(
        img: np.ndarray, faces: List[Any], padding: float = 0.4
    ) -> Optional[Tuple[int, int, int, int]]:
        if not faces:
            return None

        h, w = img.shape[:2]
        boxes = []
        for det in faces:
            bbox = det.bounding_box
            boxes.append((
                int(bbox.origin_x), int(bbox.origin_y),
                int(bbox.width), int(bbox.height),
            ))

        x_min = min(b[0] for b in boxes)
        y_min = min(b[1] for b in boxes)
        x_max = max(b[0] + b[2] for b in boxes)
        y_max = max(b[1] + b[3] for b in boxes)

        box_w = x_max - x_min
        box_h = y_max - y_min
        pad_x = int(box_w * padding)
        pad_y = int(box_h * padding)

        cx = max(0, x_min - pad_x)
        cy = max(0, y_min - pad_y)
        cw = min(w - cx, box_w + 2 * pad_x)
        ch = min(h - cy, box_h + 2 * pad_y)

        return (cx, cy, cw, ch)

    @staticmethod
    def smart_crop(
        image_path: str | Path,
        output_path: str | Path,
        padding: float = 1.0,
        aspect_ratio: Optional[float] = None,
    ) -> bool:
        img = cv2.imread(str(image_path))
        if img is None:
            return False

        # ── Mutualisation : réutiliser les visages du scoring ──
        cache_key = str(image_path)
        with PhotoScorer._face_cache_lock:
            cached = PhotoScorer._face_cache.get(cache_key)
        if cached is not None:
            cached_faces, cached_shape = cached
            if cached_shape == img.shape:
                faces = cached_faces
            else:
                # Image redimensionnée ou réécrite → ne pas utiliser le cache obsolète
                with PhotoScorer._face_cache_lock:
                    PhotoScorer._face_cache.pop(cache_key, None)
                faces = None
        else:
            faces = None

        if faces is None:
            fd_model = _ensure_model("face_detector")
            fd_options = vision.FaceDetectorOptions(
                base_options=python.BaseOptions(model_asset_path=fd_model),
                running_mode=vision.RunningMode.IMAGE,
            )
            with vision.FaceDetector.create_from_options(fd_options) as fd:
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = fd.detect(mp_img)
                if not result.detections:
                    return False
                faces = result.detections

        region = PhotoScorer.face_safety_region(img, faces, padding=padding)
        if region is None:
            return False

        x, y, rw, rh = region

        if aspect_ratio is not None:
            current_ratio = rw / rh if rh > 0 else 1.0
            if current_ratio > aspect_ratio:
                new_w = int(rh * aspect_ratio)
                x += (rw - new_w) // 2
                rw = new_w
            else:
                new_h = int(rw / aspect_ratio)
                y += (rh - new_h) // 2
                rh = new_h

        cropped = img[y:y + rh, x:x + rw]
        if cropped.size > 0:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(output_path), cropped)
            return True

        return False

    @staticmethod
    def fix_exif_rotation(image_path: str | Path, output_dir: str | Path) -> str | None:
        """Corrige la rotation EXIF d'une image sans modifier l'original.

        Lit la balise EXIF 0x0112 (Orientation) et applique la
        rotation correspondante avec Pillow.  Écrit une copie
        pivotée dans `output_dir` et retourne le nouveau chemin.
        Retourne None si aucune correction n'est nécessaire.

        Args:
            image_path: chemin de l'image source (jamais modifié)
            output_dir: répertoire où écrire la copie pivotée

        Returns:
            Chemin de la copie pivotée, ou None si pas de rotation.
        """
        from PIL import Image

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            with Image.open(image_path) as img:
                exif = img._getexif() or {}
                orientation = exif.get(0x0112)

            if orientation is None:
                return None

            # Rouvrir pour modification (Image.open en with bloque l'écriture)
            img = Image.open(image_path)
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation == 6:
                img = img.rotate(270, expand=True)
            elif orientation == 8:
                img = img.rotate(90, expand=True)
            else:
                img.close()
                return None

            import hashlib
            src_name = Path(image_path).name
            src_path = str(Path(image_path).resolve())
            path_hash = hashlib.sha256(src_path.encode()).hexdigest()[:12]
            rotated_name = f"rotated_{path_hash}_{src_name}"
            out_path = str(output_dir / rotated_name)
            img.save(out_path)
            img.close()
            return out_path
        except (OSError, IOError, AttributeError, KeyError):
            return None


class PhotoDispatcher:
    """Répartit les photos notées en spreads héroïque / duo / grille.

    Dispatch 7/13/80 par percentile (d'après le complément Athéna) :
      - Top 7%   → Héroïque (1 photo pleine page)
      - 7%-20%   → Duo (2 photos par page)
      - 80% rest → Grille (4-6 photos par page)
    """

    def __init__(self, heroique_pct: float = 0.07, duo_pct: float = 0.13) -> None:
        self.heroique_pct = heroique_pct
        self.duo_pct = duo_pct

    def dispatch(
        self, photo_scores: List[Tuple[str, float, Dict[str, float]]]
    ) -> Dict[str, List[Tuple[str, float, Dict[str, float]]]]:
        if not photo_scores:
            return {"heroique": [], "duo": [], "grille": []}

        sorted_ps = sorted(photo_scores, key=lambda x: x[1], reverse=True)
        n = len(sorted_ps)

        n_heroique = max(1, round(n * self.heroique_pct))
        n_duo = max(1, round(n * self.duo_pct))

        if n_heroique + n_duo >= n:
            n_heroique = max(1, n // 4)
            n_duo = max(1, n // 3)
            n_duo = min(n_duo, n - n_heroique)

        return {
            "heroique": sorted_ps[:n_heroique],
            "duo": sorted_ps[n_heroique:n_heroique + n_duo],
            "grille": sorted_ps[n_heroique + n_duo:],
        }

    def dispatch_with_labels(
        self, photo_scores: List[Tuple[str, float, Dict[str, float]]]
    ) -> List[Tuple[str, float, Dict[str, float], str]]:
        buckets = self.dispatch(photo_scores)
        results = []
        for spread_type in ("heroique", "duo", "grille"):
            for path, score, details in buckets[spread_type]:
                results.append((path, score, details, spread_type))
        results.sort(key=lambda x: x[1], reverse=True)
        return results


# ── Utilitaires EXIF ─────────────────────────────────────────────────

def extract_exif_date(image_path: str | Path) -> Optional[datetime]:
    """Extrait la date de prise de vue depuis les métadonnées EXIF."""
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            exif = img._getexif()
        if not exif:
            return None

        for tag_id in (36867, 36868, 306):
            raw = exif.get(tag_id)
            if raw and isinstance(raw, str):
                try:
                    return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass
        return None
    except Exception:
        return None


def sort_by_exif_date(
    photo_paths: List[Path], strict: bool = False
) -> List[Path]:
    dated = []
    undated = []
    for p in photo_paths:
        dt = extract_exif_date(p)
        if dt:
            dated.append((dt, p))
        else:
            undated.append(p)
    dated.sort(key=lambda x: x[0])
    result = [p for _, p in dated]
    if not strict:
        result.extend(sorted(undated, key=lambda p: str(p)))
    return result


def group_photos_by_exif_month(
    photo_files: List[Path],
) -> List[Tuple[str, List[Path]]]:
    from collections import OrderedDict

    month_names = [
        "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
    ]

    months: OrderedDict = OrderedDict()
    undated = []

    sorted_photos = sort_by_exif_date(photo_files)

    for fp in sorted_photos:
        dt = extract_exif_date(fp)
        if dt:
            month_name = month_names[dt.month - 1]
            if month_name not in months:
                months[month_name] = []
            months[month_name].append(fp)
        else:
            undated.append(fp)

    result = list(months.items())
    if undated:
        result.append(("Non classé", undated))
    return result


def find_micro_events(
    photo_files: List[Path], max_gap_hours: float = 2.0
) -> List[List[Path]]:
    sorted_photos = sort_by_exif_date(photo_files)
    events = []
    current_event = []

    for fp in sorted_photos:
        dt = extract_exif_date(fp)
        if dt is None:
            if current_event:
                events.append(current_event)
                current_event = []
            events.append([fp])
            continue
        if current_event:
            last_dt = extract_exif_date(current_event[-1])
            if last_dt is not None:
                gap = (dt - last_dt).total_seconds() / 3600.0
                if gap > max_gap_hours:
                    events.append(current_event)
                    current_event = []
        current_event.append(fp)
    if current_event:
        events.append(current_event)
    return events


def export_scoring_report(
    photo_scores: List[Tuple[str, float, Dict[str, float]]],
    dispatch: Dict[str, List],
    output_path: str | Path,
) -> None:
    report: Dict[str, Any] = {
        "config": {
            "heroique_pct": 7,
            "duo_pct": 13,
            "grille_pct": 80,
            "weights": SCORE_WEIGHTS,
        },
        "dispatch": {
            "heroique": [p for p, _, _ in dispatch["heroique"]],
            "duo": [p for p, _, _ in dispatch["duo"]],
            "grille": [p for p, _, _ in dispatch["grille"]],
        },
        "scores": {},
        "summary": {
            "total_photos": len(photo_scores),
            "heroique_count": len(dispatch["heroique"]),
            "duo_count": len(dispatch["duo"]),
            "grille_count": len(dispatch["grille"]),
        },
    }
    for path, total, details in sorted(photo_scores, key=lambda x: x[1], reverse=True):
        report["scores"][str(path)] = {"total": round(total, 4), "details": details}
    if dispatch["heroique"]:
        report["summary"]["heroique_min_score"] = round(
            dispatch["heroique"][-1][1], 4
        )
    if dispatch["duo"]:
        report["summary"]["duo_min_score"] = round(
            dispatch["duo"][-1][1], 4
        )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
