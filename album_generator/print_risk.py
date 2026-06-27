"""
Module de pénalité d'impression — détection des artefacts de retouche.

Calcule une pénalité `print_risk ∈ [0.0, 0.30]` qui vient pondérer
le score de dispatch à la baisse quand la retouche introduit des
artefacts visibles à l'impression (bruit amplifié, halos, perte de texture).

Les 3 détecteurs (recalibrés pour éviter de confondre amélioration et artefact) :
  1. Bruit amplifié      → +0.10  hautes fréquences résiduelles après flou bilatéral
  2. Halos de sharpening → +0.10  overshoot local aux transitions fortes
  3. Perte de texture    → +0.05  lissage excessif des détails fins

Usage :
    from album_generator.print_risk import compute_print_penalty

    penalty = compute_print_penalty(original_bgr, enhanced_bgr)
    adjusted_score = raw_score * (1.0 - penalty)
"""

from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from typing import Tuple


def compute_print_penalty(
    original: np.ndarray,
    enhanced: np.ndarray,
) -> float:
    """Calcule la pénalité d'impression entre l'image originale et retouchée.

    Args:
        original: Image BGR originale (uint8).
        enhanced: Image BGR après retouche (uint8).

    Returns:
        Pénalité ∈ [0.0, 0.30].  0.0 = aucune dégradation,
        0.30 = dégradation maximale.
    """
    # Réduire les deux à la même taille si nécessaire
    if original.shape != enhanced.shape:
        enhanced = cv2.resize(enhanced,
                              (original.shape[1], original.shape[0]),
                              interpolation=cv2.INTER_LINEAR)

    # Convertir en float pour les calculs
    orig_f = original.astype(np.float32)
    enh_f = enhanced.astype(np.float32)

    penalty = 0.0

    # ── 1. Bruit amplifié (+0.10) ──
    noise_penalty = _noise_blowup(orig_f, enh_f)
    penalty += noise_penalty

    # ── 2. Halos de sharpening (+0.10 max) ──
    halo_penalty = _halo_detection(orig_f, enh_f)
    penalty += halo_penalty

    # ── 3. Perte de texture (+0.05) ──
    texture_penalty = _texture_loss(orig_f, enh_f)
    penalty += texture_penalty

    return min(penalty, 0.30)


# ── Détecteurs internes ──────────────────────────────────────────────────


def _noise_blowup(
    original: np.ndarray,
    enhanced: np.ndarray,
) -> float:
    """Détecte l'amplification du bruit après retouche.

    Utilise une approche discriminante bruit vs contraste :
      1. Applique un flou bilatéral fort (d=9, sigma=75) pour obtenir
         une version « lissée » (contours préservés, bruit supprimé).
      2. Le résidu = image - lissée est le bruit haute fréquence.
      3. Compare la variance du résidu avant/après retouche.

    Contrairement à l'écart-type des blocs (qui mesure aussi le contraste),
    le résidu bilatéral isole le bruit grain fin des variations de texture.

    Returns:
        0.10 si le bruit est amplifié de > 25 %, 0.0 sinon.
    """
    def _noise_residual_variance(img: np.ndarray) -> float:
        """Variance du résidu de bruit (haute fréquence isolée par bilateral)."""
        img_u8 = np.clip(img, 0, 255).astype(np.uint8)
        smoothed = cv2.bilateralFilter(img_u8, d=9, sigmaColor=75, sigmaSpace=75)
        residual = img_u8.astype(np.float32) - smoothed.astype(np.float32)
        return float(np.var(residual))

    orig_noise = _noise_residual_variance(original)
    enh_noise = _noise_residual_variance(enhanced)

    # Seuil à 25 % (plus conservateur que 15 %) — évite les faux positifs
    # quand le contraste augmente naturellement sans bruit additionnel.
    if orig_noise > 0.1 and enh_noise > orig_noise * 1.25:
        # Proportionnel à l'augmentation, capé à 0.10
        ratio = min(enh_noise / max(orig_noise, 1e-6), 3.0)
        return min((ratio - 1.0) * 0.20, 0.10)
    return 0.0


def _halo_detection(
    original: np.ndarray,
    enhanced: np.ndarray,
) -> float:
    """Détecte les halos de sharpening — overshoots locaux aux transitions.

    Un vrai halo est une bande étroite (1-3 px) de luminance excessive
    immédiatement adjacente à un bord fort.  On le détecte en cherchant
    les pixels qui sont :
      1. Sur un gradient fort (bord)
      2. PLUS lumineux que leurs voisins dans la direction du gradient
         ET plus lumineux que dans l'image originale au même point
      3. Suffisamment rares (< 3 % des pixels de bord)

    Returns:
        Pénalité ∈ [0.0, 0.10], proportionnelle à la densité de halos.
    """
    # Travailler sur le canal L (LAB)
    lab_o = cv2.cvtColor(np.clip(original, 0, 255).astype(np.uint8), cv2.COLOR_BGR2LAB)
    lab_e = cv2.cvtColor(np.clip(enhanced, 0, 255).astype(np.uint8), cv2.COLOR_BGR2LAB)
    l_o = lab_o[:, :, 0].astype(np.float32)
    l_e = lab_e[:, :, 0].astype(np.float32)

    # Gradient Sobel de l'image retouchée
    grad_x = cv2.Sobel(l_e, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(l_e, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.sqrt(grad_x ** 2 + grad_y ** 2)

    # Seuil de gradient fort (top 15 %)
    grad_threshold = np.percentile(grad_mag, 85)

    # Pixels de bord fort
    strong_edges = grad_mag > grad_threshold

    # Direction du gradient normalisée
    grad_dir_x = np.divide(grad_x, grad_mag, out=np.zeros_like(grad_x), where=grad_mag > 1e-6)
    grad_dir_y = np.divide(grad_y, grad_mag, out=np.zeros_like(grad_y), where=grad_mag > 1e-6)

    # Pour chaque pixel de bord, vérifier s'il est un maximum local
    # dans la direction du gradient (signe d'overshoot/halo)
    h, w = l_e.shape
    overshoot_count = 0
    edge_count = max(np.count_nonzero(strong_edges), 1)

    # Échantillonner pour la performance (vérifier 1 pixel sur 4 le long des bords)
    edge_ys, edge_xs = np.where(strong_edges)
    sample_mask = np.zeros(len(edge_ys), dtype=bool)
    sample_mask[::4] = True  # 25% des pixels de bord
    edge_ys = edge_ys[sample_mask]
    edge_xs = edge_xs[sample_mask]
    sampled_edge_count = max(len(edge_ys), 1)

    for i in range(len(edge_ys)):
        y, x = edge_ys[i], edge_xs[i]
        dx = grad_dir_x[y, x]
        dy = grad_dir_y[y, x]

        # Voisin dans la direction du gradient (positif et négatif)
        nx_pos = int(round(x + dx))
        ny_pos = int(round(y + dy))
        nx_neg = int(round(x - dx))
        ny_neg = int(round(y - dy))

        # Vérifier les bornes
        if not (0 <= nx_pos < w and 0 <= ny_pos < h):
            continue
        if not (0 <= nx_neg < w and 0 <= ny_neg < h):
            continue

        center = l_e[y, x]
        neighbor_pos = l_e[ny_pos, nx_pos]
        neighbor_neg = l_e[ny_neg, nx_neg]

        # Halo = centre plus lumineux que les deux voisins (gradient)
        # ET plus lumineux que l'original au même point
        orig_val = l_o[y, x]
        if center > neighbor_pos and center > neighbor_neg and center > orig_val + 3.0:
            overshoot_count += 1

    halo_ratio = overshoot_count / sampled_edge_count

    # Pénalité : halo_ratio > 1% → significatif
    if halo_ratio > 0.01:
        return min(halo_ratio * 1.0, 0.10)
    return 0.0


def _texture_loss(
    original: np.ndarray,
    enhanced: np.ndarray,
) -> float:
    """Détecte la perte de texture fine (bilateral trop agressif).

    Compare la variance du Laplacian (proxy de texture fine) entre
    l'original et l'image retouchée.  Une baisse > 10 % indique
    que le bilateral filter a lissé des détails qui ne sont pas
    du bruit.

    Returns:
        0.05 si perte de texture détectée, 0.0 sinon.
    """
    def _laplacian_variance(img: np.ndarray) -> float:
        gray = cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    orig_lap = _laplacian_variance(original)
    enh_lap = _laplacian_variance(enhanced)

    # Seulement si l'original avait une texture mesurable
    # et que la retouche l'a significativement réduite
    if orig_lap > 10.0 and enh_lap < orig_lap * 0.90:
        return 0.05
    return 0.0


# ── Utilitaire : pénalité pour une photo sur disque ─────────────────────


def compute_print_penalty_file(
    original_path: str | Path,
    enhanced_path: str | Path,
) -> float:
    """Calcule la pénalité d'impression entre deux fichiers photo.

    Args:
        original_path: Chemin de la photo originale.
        enhanced_path: Chemin de la photo retouchée.

    Returns:
        Pénalité ∈ [0.0, 0.30].
    """
    orig = cv2.imread(str(original_path))
    enh = cv2.imread(str(enhanced_path))
    if orig is None:
        raise FileNotFoundError(f"Impossible de lire l'original : {original_path}")
    if enh is None:
        raise FileNotFoundError(f"Impossible de lire l'image retouchée : {enhanced_path}")
    return compute_print_penalty(orig, enh)
