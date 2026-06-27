#!/usr/bin/env python3
"""
video_processing.py — Extraction des meilleures frames d'une vidéo.

Wrapper autour du pipeline video_best_frames (OpenCV/FFmpeg) pour extraire
les frames les plus intéressantes d'une vidéo : netteté, visages, scènes.

Usage:
    from video_processing import extract_best_frames

    frames = extract_best_frames("vacances.mp4", output_dir="frames/", top_n=10)
    for f in frames:
        print(f.path, f.score)
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ── Constantes ────────────────────────────────────────────────────────────────

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mts", ".ts", ".3gp", ".webm"}
DEFAULT_TOP_N = 30         # Nombre max de frames à extraire
MIN_SHARPNESS = 15.0       # Seuil minimum de netteté (Laplacian)
FRAME_INTERVAL = 0.5       # Intervalle minimum entre deux frames (secondes)
SIMILARITY_THRESHOLD = 0.92  # Seuil de similarité (histogramme) pour dédoublonnage


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ExtractedFrame:
    """Une frame extraite d'une vidéo."""
    timestamp_sec: float        # Position dans la vidéo
    path: str                   # Chemin absolu du fichier JPEG
    score: float = 0.0          # Score qualité (0.0 - 1.0)
    sharpness: float = 0.0      # Netteté (variance du Laplacian)
    width: int = 0
    height: int = 0
    has_face: bool = False
    face_count: int = 0

    @property
    def timecode(self) -> str:
        """Retourne le timestamp au format HH:MM:SS.mmm."""
        h = int(self.timestamp_sec // 3600)
        m = int((self.timestamp_sec % 3600) // 60)
        s = self.timestamp_sec % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}"


# ── Extracteur de frames ──────────────────────────────────────────────────────

class VideoFrameExtractor:
    """Extraction et scoring des meilleures frames d'une vidéo.

    Pipeline :
    1. Analyse de la vidéo (durée, résolution, fps)
    2. Échantillonnage régulier ou détection de scènes
    3. Scoring : netteté + visages (MediaPipe)
    4. Dédoublonnage par similarité d'histogramme
    5. Sélection des N meilleures
    """

    def __init__(
        self,
        top_n: int = DEFAULT_TOP_N,
        min_sharpness: float = MIN_SHARPNESS,
        frame_interval: float = FRAME_INTERVAL,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        use_face_detection: bool = True,
    ):
        self.top_n = top_n
        self.min_sharpness = min_sharpness
        self.frame_interval = frame_interval
        self.similarity_threshold = similarity_threshold
        self.use_face_detection = use_face_detection
        self._face_detector = None

    def _get_face_detector(self):
        """Lazy-load du détecteur de visages MediaPipe."""
        if self._face_detector is None and self.use_face_detection:
            try:
                import mediapipe as mp
                self._face_detector = mp.solutions.face_detection.FaceDetection(
                    model_selection=1, min_detection_confidence=0.5
                )
            except ImportError:
                logger.warning("MediaPipe non disponible — détection de visages désactivée")
                self.use_face_detection = False
        return self._face_detector

    def extract(
        self,
        video_path: str,
        output_dir: str,
        progress_callback=None,
    ) -> List[ExtractedFrame]:
        """Extrait les meilleures frames d'une vidéo.

        Args:
            video_path: Chemin vers le fichier vidéo
            output_dir: Dossier de sortie pour les frames JPEG
            progress_callback: Fonction optionnelle (current, total, message)

        Returns:
            Liste des meilleures frames, triées par score décroissant
        """
        vp = Path(video_path)
        if not vp.exists():
            raise FileNotFoundError(f"Vidéo introuvable: {video_path}")
        if vp.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError(f"Extension non supportée: {vp.suffix}")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 1. Ouvrir la vidéo
        cap = cv2.VideoCapture(str(vp))
        if not cap.isOpened():
            raise RuntimeError(f"Impossible d'ouvrir la vidéo: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = total_frames / fps if fps > 0 else 0

        logger.info(
            f"Vidéo: {vp.name} | {total_frames} frames | {fps:.1f} fps | "
            f"{duration:.1f}s | {vp.stat().st_size // 1024 // 1024} MB"
        )

        if progress_callback:
            progress_callback(0, total_frames, f"Analyse de {vp.name}...")

        # 2. Échantillonnage + scoring
        frames: List[ExtractedFrame] = []
        last_hist: Optional[np.ndarray] = None
        frame_count = 0
        sample_interval = max(1, int(fps * self.frame_interval))

        if self.use_face_detection:
            detector = self._get_face_detector()

        while True:
            ret, img = cap.read()
            if not ret:
                break

            frame_count += 1
            if frame_count % sample_interval != 0:
                continue

            timestamp = frame_count / fps
            if progress_callback and frame_count % (sample_interval * 10) == 0:
                progress_callback(frame_count, total_frames,
                                  f"Scan {frame_count}/{total_frames}...")

            # Score de netteté
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()

            if sharpness < self.min_sharpness:
                continue

            # Détection de visages
            face_count = 0
            has_face = False
            if self.use_face_detection and detector:
                try:
                    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    results = detector.process(rgb)
                    if results.detections:
                        face_count = len(results.detections)
                        has_face = True
                except Exception:
                    pass

            # Dédoublonnage par similarité d'histogramme
            if last_hist is not None:
                hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
                hist = cv2.normalize(hist, hist).flatten()
                similarity = cv2.compareHist(last_hist, hist, cv2.HISTCMP_CORREL)
                if similarity > self.similarity_threshold:
                    continue
                last_hist = hist
            else:
                hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
                last_hist = cv2.normalize(hist, hist).flatten()

            # Score composite
            score = self._compute_score(sharpness, face_count, has_face)

            # Sauvegarde
            frame_filename = f"{vp.stem}_frame_{frame_count:06d}.jpg"
            frame_path = str(output_path / frame_filename)
            cv2.imwrite(frame_path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])

            h, w = img.shape[:2]
            frames.append(ExtractedFrame(
                timestamp_sec=timestamp,
                path=frame_path,
                score=score,
                sharpness=sharpness,
                width=w,
                height=h,
                has_face=has_face,
                face_count=face_count,
            ))

        cap.release()

        # 3. Trier et garder les meilleures
        frames.sort(key=lambda f: f.score, reverse=True)
        best = frames[:self.top_n]

        # Supprimer les frames non retenues
        kept_paths = {f.path for f in best}
        for f in frames[self.top_n:]:
            try:
                Path(f.path).unlink(missing_ok=True)
            except OSError:
                pass

        if progress_callback:
            progress_callback(total_frames, total_frames,
                              f"✅ {len(best)} frames extraites de {len(frames)} candidates")

        logger.info(f"Extraction terminée: {len(best)} meilleures frames sur {len(frames)} candidates")
        return best

    def _compute_score(self, sharpness: float, face_count: int, has_face: bool) -> float:
        """Calcule un score composite entre 0.0 et 1.0.

        Poids :
        - Netteté (normalisée) : 60%
        - Présence de visages : 40%
        """
        # Normalisation de la netteté (empirique : une bonne photo > 100)
        sharp_norm = min(sharpness / 100.0, 1.0)

        face_score = 0.4 if has_face else 0.0
        if face_count > 1:
            face_score = min(0.4 + 0.1 * (face_count - 1), 0.6)

        score = 0.6 * sharp_norm + face_score
        return round(min(score, 1.0), 4)

    def get_video_metadata(self, video_path: str) -> Dict[str, Any]:
        """Extrait les métadonnées d'une vidéo via OpenCV + FFmpeg probe."""
        meta: Dict[str, Any] = {}

        # OpenCV
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            meta["total_frames"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            meta["fps"] = round(cap.get(cv2.CAP_PROP_FPS), 2)
            meta["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            meta["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            meta["duration_sec"] = round(meta["total_frames"] / meta["fps"], 2) if meta["fps"] > 0 else 0
            cap.release()

        # FFprobe pour infos supplémentaires (codec, date, etc.)
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", video_path],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                meta["codec"] = data.get("streams", [{}])[0].get("codec_name", "")
                meta["bitrate"] = data.get("format", {}).get("bit_rate", "")
                meta["creation_time"] = data.get("format", {}).get("tags", {}).get("creation_time", "")
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass

        meta["path"] = str(Path(video_path).resolve())
        meta["filename"] = Path(video_path).name
        meta["size_bytes"] = Path(video_path).stat().st_size

        return meta


# ── Fonctions utilitaires ──────────────────────────────────────────────────────

def extract_best_frames(
    video_path: str,
    output_dir: str = "",
    top_n: int = DEFAULT_TOP_N,
    return_metadata: bool = False,
) -> List[ExtractedFrame]:
    """Fonction d'appel rapide pour extraire les meilleures frames.

    Args:
        video_path: Chemin vers la vidéo
        output_dir: Dossier de sortie (auto: {video_stem}_frames/)
        top_n: Nombre de frames à garder
        return_metadata: Si True, retourne aussi les métadonnées dans le log

    Returns:
        Liste des meilleures frames extraites
    """
    if not output_dir:
        stem = Path(video_path).stem
        output_dir = f"{stem}_frames/"

    extractor = VideoFrameExtractor(top_n=top_n)
    return extractor.extract(video_path, output_dir)


def get_video_metadata(video_path: str) -> Dict[str, Any]:
    """Obtient les métadonnées d'une vidéo."""
    extractor = VideoFrameExtractor()
    return extractor.get_video_metadata(video_path)


def batch_extract_frames(
    video_dir: str,
    output_base_dir: str = "",
    top_n: int = DEFAULT_TOP_N,
    progress_callback=None,
) -> Dict[str, List[ExtractedFrame]]:
    """Extrait les frames de toutes les vidéos d'un dossier.

    Returns:
        Dict: {video_name: [ExtractedFrame, ...]}
    """
    vd = Path(video_dir)
    if not vd.is_dir():
        raise NotADirectoryError(f"Dossier introuvable: {video_dir}")

    videos = sorted(p for p in vd.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:
        logger.warning(f"Aucune vidéo trouvée dans {video_dir}")
        return {}

    results: Dict[str, List[ExtractedFrame]] = {}
    total = len(videos)

    for i, vp in enumerate(videos):
        stem = vp.stem
        out_dir = (Path(output_base_dir) / stem) if output_base_dir else f"{stem}_frames/"

        if progress_callback:
            progress_callback(i, total, f"[{i+1}/{total}] {vp.name}...")

        logger.info(f"Traitement [{i+1}/{total}]: {vp.name}")
        extractor = VideoFrameExtractor(top_n=top_n)
        frames = extractor.extract(str(vp), str(out_dir))
        results[stem] = frames
        logger.info(f"  → {len(frames)} frames extraites")

    if progress_callback:
        progress_callback(total, total, f"✅ {total} vidéos traitées")

    return results
