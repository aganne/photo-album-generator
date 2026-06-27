"""
Module de retouche photo automatique — pipeline OpenCV 5 étapes.

Pipeline recommandée (Athéna, §4.2) :
  1. Balance des blancs (Grey World)      → qualité perçue
  2. Bilateral filter (d=5, sigma=50)     → réduction bruit
  3. CLAHE sur L (clip=2.0, tile=8)       → contraste local
  4. Local Contrast Enhancement (r=80, a=0.3)  → GIMP « luminosité détails »
  5. Unsharp Mask (r=1.5, a=0.8, th=2)    → netteté

Usage :
    from album_generator.enhance import auto_enhance, batch_enhance

    enhanced = auto_enhance(img_bgr, level="default")
    paths = batch_enhance(photo_paths, output_dir, level="default")
"""

from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Literal, Dict, Any

EnhanceLevel = Literal["default", "strong"]

# ── Paramètres par niveau ──────────────────────────────────────────────

ENHANCE_PARAMS: Dict[EnhanceLevel, Dict[str, Any]] = {
    "default": {
        "white_balance": "greyworld",
        "denoise": {"d": 5, "sigma_color": 50, "sigma_space": 50},
        "clahe": {"clip_limit": 2.0, "tile_size": 8},
        "local_contrast": {"radius": 80, "amount": 0.30},
        "unsharp_mask": {"radius": 1.5, "amount": 0.8, "threshold": 2},
    },
    "strong": {
        "white_balance": "greyworld",
        "denoise": {"d": 9, "sigma_color": 75, "sigma_space": 75},
        "clahe": {"clip_limit": 3.0, "tile_size": 6},
        "local_contrast": {"radius": 120, "amount": 0.50},
        "unsharp_mask": {"radius": 2.0, "amount": 1.2, "threshold": 3},
    },
}


def auto_enhance(
    img: np.ndarray,
    level: EnhanceLevel = "default",
    params: Optional[Dict[str, Any]] = None,
) -> np.ndarray:
    """Pipeline de retouche complète — 5 étapes OpenCV (~100 ms/photo).

    Args:
        img: Image BGR OpenCV (np.ndarray, uint8).
        level: Niveau de retouche — "default" (doux) ou "strong".
        params: Paramètres personnalisés (surcharge ENHANCE_PARAMS[level]).

    Returns:
        Image retouchée (BGR, uint8).
    """
    base = ENHANCE_PARAMS[level]
    overrides = params or {}
    p = {**base, **overrides}
    for key in ("denoise", "clahe", "local_contrast", "unsharp_mask"):
        p[key] = {**base.get(key, {}), **overrides.get(key, {})}

    # ── 1. Balance des blancs (Grey World) ──
    if p.get("white_balance") == "greyworld":
        img = _white_balance_greyworld(img)

    # ── 2. Réduction de bruit (Bilateral filter) ──
    dn = p.get("denoise", {})
    if dn.get("d", 0) > 0:
        img = cv2.bilateralFilter(
            img,
            dn.get("d", 5),
            dn.get("sigma_color", 50),
            dn.get("sigma_space", 50),
        )

    # ── 3. CLAHE sur le canal L (LAB) ──
    clahe_cfg = p.get("clahe", {})
    if clahe_cfg.get("clip_limit", 0) > 0:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(
            clipLimit=clahe_cfg.get("clip_limit", 2.0),
            tileGridSize=(clahe_cfg.get("tile_size", 8),) * 2,
        )
        l_ch = clahe.apply(l_ch)
        lab = cv2.merge([l_ch, a_ch, b_ch])
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # ── 4. Local Contrast Enhancement (GIMP « luminosité détails ») ──
    lc = p.get("local_contrast", {})
    if lc.get("amount", 0) > 0:
        img = _local_contrast_enhancement(
            img, lc.get("radius", 80), lc.get("amount", 0.30)
        )

    # ── 5. Unsharp Mask (netteté) ──
    usm = p.get("unsharp_mask", {})
    if usm.get("amount", 0) > 0:
        img = _unsharp_mask_luminance(
            img,
            usm.get("radius", 1.5),
            usm.get("amount", 0.8),
            usm.get("threshold", 2),
        )

    return img


# ── Fonctions internes ───────────────────────────────────────────────────


def _white_balance_greyworld(img: np.ndarray) -> np.ndarray:
    """Balance des blancs — hypothèse Grey World (R̅=G̅=B̅ en moyenne)."""
    result = img.astype(np.float32)
    avg_r = np.mean(result[:, :, 2])
    avg_g = np.mean(result[:, :, 1])
    avg_b = np.mean(result[:, :, 0])
    avg_gray = (avg_r + avg_g + avg_b) / 3.0

    result[:, :, 2] *= avg_gray / max(avg_r, 1e-6)
    result[:, :, 1] *= avg_gray / max(avg_g, 1e-6)
    result[:, :, 0] *= avg_gray / max(avg_b, 1e-6)

    return np.clip(result, 0, 255).astype(np.uint8)


def _local_contrast_enhancement(
    img: np.ndarray, radius: int = 80, amount: float = 0.30
) -> np.ndarray:
    """Équivalent GIMP « luminosité des détails » / Lightroom Clarity.

    Un grand flou gaussien capture les transitions lentes (tons moyens).
    La différence avec l'original est réinjectée avec un faible poids,
    créant du « pop » visuel sans halos de sharpening.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)

    sigma = radius / 3.0
    ksize = int(2 * round(radius) + 1) | 1  # impair
    ksize = min(ksize, 501)  # OpenCV limite la taille du kernel

    l_float = l_ch.astype(np.float32)
    blurred = cv2.GaussianBlur(l_float, (ksize, ksize), sigma)
    mask = l_float - blurred
    l_enhanced = np.clip(l_float + amount * mask, 0, 255).astype(np.uint8)

    lab_enhanced = cv2.merge([l_enhanced, a_ch, b_ch])
    return cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)


def _unsharp_mask_luminance(
    img: np.ndarray,
    radius: float = 1.5,
    amount: float = 0.8,
    threshold: int = 2,
) -> np.ndarray:
    """Unsharp mask sur la luminance uniquement (canal L, LAB).

    Évite les artefacts de couleur en ne touchant qu'à la luminosité.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)

    sigma = max(radius / 3.0, 0.5)
    ksize = int(2 * round(radius) + 1) | 1  # impair

    l_float = l_ch.astype(np.float32)
    blurred = cv2.GaussianBlur(l_float, (ksize, ksize), sigma)
    mask = l_float - blurred

    if threshold > 0:
        mask = np.where(np.abs(mask) < threshold, 0.0, mask)

    l_sharp = np.clip(l_float + amount * mask, 0, 255).astype(np.uint8)

    lab_enhanced = cv2.merge([l_sharp, a_ch, b_ch])
    return cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)


# ── Batch processing ─────────────────────────────────────────────────────


def auto_enhance_file(
    input_path: str | Path,
    output_dir: str | Path,
    level: EnhanceLevel = "default",
    max_dim: Optional[int] = None,
) -> str:
    """Charge, retouche et sauvegarde une photo sur disque.

    Args:
        input_path: Chemin de la photo source.
        output_dir: Dossier de destination.
        level: "default" ou "strong".
        max_dim: Si spécifié, réduit la photo à max_dim px de côté max
                 avant retouche (puis réagrandit à la taille d'origine).

    Returns:
        Chemin absolu du fichier retouché sauvegardé.
    """
    img = cv2.imread(str(input_path))
    if img is None:
        raise FileNotFoundError(f"Impossible de lire : {input_path}")

    original_shape = img.shape[:2]

    # Optionnel : réduire pour la retouche (gain de temps)
    if max_dim and max_dim > 0 and max(img.shape[:2]) > max_dim:
        h, w = img.shape[:2]
        scale = max_dim / max(h, w)
        img = cv2.resize(
            img, (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )

    enhanced = auto_enhance(img, level=level)

    # Remettre à la taille originale si réduit
    if max_dim and enhanced.shape[:2] != original_shape:
        oh, ow = original_shape
        enhanced = cv2.resize(enhanced, (ow, oh), interpolation=cv2.INTER_LINEAR)

    import hashlib
    source = Path(input_path).resolve()
    path_hash = hashlib.sha256(str(source).encode()).hexdigest()[:12]
    output_path = Path(output_dir) / f"{path_hash}_{source.name}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), enhanced)
    return str(output_path.resolve())


def batch_enhance(
    photo_paths: List[str | Path],
    output_dir: str | Path,
    level: EnhanceLevel = "default",
    max_workers: int = 4,
    max_dim: Optional[int] = None,
) -> List[str]:
    """Retouche un lot de photos en parallèle (ThreadPoolExecutor).

    Args:
        photo_paths: Liste de chemins vers les photos sources.
        output_dir: Dossier de sortie.
        level: "default" (doux) ou "strong".
        max_workers: Nombre de threads (4-8 recommandé).
        max_dim: Si spécifié, réduit avant retouche (gain ×2-3).

    Returns:
        Liste des chemins des fichiers retouchés (ordre non garanti).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results: List[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(auto_enhance_file, p, out, level, max_dim): p
            for p in photo_paths
        }
        for future in as_completed(futures):
            src = futures[future]
            try:
                result_path = future.result()
                results.append(result_path)
            except Exception as exc:
                print(f"❌ {src}: {exc}")

    return results
