"""
Extraction de palette chromatique via l'API Colormind.

Génère une palette de 5 couleurs à partir des meilleures photos de l'album
et l'applique au rendu CSS via substitution des couleurs de la palette Soleil.

Usage :
    from album_generator.colors import extract_palette, generate_dynamic_css

    palette = extract_palette(photo_scores[:5])      # → dict palette
    css = generate_dynamic_css(palette)               # → CSS dynamique
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from album_generator.config import PALETTES_DISPONIBLES

# ── URL de l'API Colormind (gratuite, pas de token) ──────────────────
COLORMIND_API_URL = "https://colormind.io/api/"

# ── Mapping Colormind → couleurs CSS ─────────────────────────────────
# Colormind renvoie 5 couleurs [R,G,B]. Le mapping définit leur usage
# dans l'album : fonds, bandes, texte, accents.
#
# Index 0 → bg_start       (fond dégradé haut)
# Index 1 → text_primary   (texte principal) / band_top
# Index 2 → bg_mid         (fond milieu) / accent_1
# Index 3 → bg_end         (fond dégradé bas) / accent_2
# Index 4 → band_bottom    (bande bas) / deco_line

# ── Palette Soleil (fallback) ────────────────────────────────────────
_SOLEIL_KEYS_ORDER = [
    "bg_start", "bg_mid", "bg_end",
    "band_top", "band_bottom",
    "text_primary", "text_secondary", "text_tertiary",
    "accent_1", "accent_2", "accent_3",
    "photo_border", "deco_line",
]


def _rgb_to_hex(rgb: List[int]) -> str:
    """Convertit [R, G, B] en chaîne hex #RRGGBB."""
    r, g, b = [max(0, min(255, int(c))) for c in rgb]
    return f"#{r:02x}{g:02x}{b:02x}"


def _hex_to_rgb(hex_color: str) -> List[int]:
    """Convertit #RRGGBB en [R, G, B]."""
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _blend_rgb(c1: List[int], c2: List[int], ratio: float) -> List[int]:
    """Mélange deux couleurs RGB. ratio=0 → c1, ratio=1 → c2."""
    return [
        int(c1[i] + (c2[i] - c1[i]) * ratio)
        for i in range(3)
    ]


def _get_average_color(image_path: str | Path) -> Optional[List[int]]:
    """Extrait la couleur moyenne d'une image (RGB).

    Échantillonne l'image à une résolution max pour rester rapide.
    Retourne [R, G, B] ou None si l'image est illisible.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return None

    # Réduire pour la performance (max 256 px de côté)
    h, w = img.shape[:2]
    max_dim = max(h, w)
    if max_dim > 256:
        scale = 256 / max_dim
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)

    # Moyenne BGR → RGB
    avg = cv2.mean(img)[:3]
    return [int(avg[2]), int(avg[1]), int(avg[0])]


def _call_colormind(hints: List[Any]) -> List[List[int]]:
    """Appelle l'API Colormind avec des hints de couleur.

    Args:
        hints: liste de 5 éléments, chaque élément est soit
               [R, G, B] (hint) soit "N" (modèle libre).

    Returns:
        liste de 5 couleurs [[R,G,B], ...]

    Raises:
        Exception si l'API est injoignable ou renvoie une erreur.
    """
    # Compléter à 5 avec "N" si nécessaire
    while len(hints) < 5:
        hints.append("N")
    hints = hints[:5]

    payload = json.dumps({"model": "default", "input": hints}).encode("utf-8")

    req = urllib.request.Request(
        COLORMIND_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; AlbumGenerator/1.0)",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if "result" not in data or len(data["result"]) != 5:
        raise ValueError(f"Réponse Colormind inattendue : {data}")

    return data["result"]


def _fallback_palette() -> Dict[str, Any]:
    """Retourne la palette Soleil en fallback."""
    soleil = PALETTES_DISPONIBLES.get("Soleil", {})
    if soleil:
        return dict(soleil)
    # Fallback ultime
    return {
        "name": "Soleil ☀️ (fallback)",
        "bg_start": "#fefcf5",
        "bg_mid": "#f5ede0",
        "bg_end": "#e8cfa0",
        "band_top": "#8a6a3a",
        "band_bottom": "#c49a5a",
        "text_primary": "#3a2a1a",
        "text_secondary": "#5a3a1a",
        "text_tertiary": "#8a6a3a",
        "accent_1": "#c49a5a",
        "accent_2": "#e8cfa0",
        "accent_3": "#d4b888",
        "photo_border": "#ffffff",
        "deco_line": "#c49a5a",
        "desaturation": 10,
    }


def _map_colormind_to_css(palette_rgb: List[List[int]]) -> Dict[str, Any]:
    """Convertit les 5 couleurs Colormind en dict palette complet.

    Mapping (cf. spécification) :
        [0] → bg_start
        [1] → text_primary, band_top
        [2] → bg_mid, accent_1
        [3] → bg_end, accent_2
        [4] → band_bottom, deco_line

    Les couleurs dérivées (text_secondary, text_tertiary, accent_3)
    sont générées par mélange RGB.
    """
    c = palette_rgb  # alias

    bg_start = _rgb_to_hex(c[0])
    text_primary = _rgb_to_hex(c[1])
    band_top = _rgb_to_hex(c[1])
    bg_mid = _rgb_to_hex(c[2])
    accent_1 = _rgb_to_hex(c[2])
    bg_end = _rgb_to_hex(c[3])
    accent_2 = _rgb_to_hex(c[3])
    band_bottom = _rgb_to_hex(c[4])
    deco_line = _rgb_to_hex(c[4])

    # Couleurs dérivées
    tp_rgb = c[1]
    a1_rgb = c[2]

    # text_secondary = text_primary éclairci de 25% vers blanc
    text_secondary = _rgb_to_hex(_blend_rgb(tp_rgb, [255, 255, 255], 0.25))
    # text_tertiary = text_primary éclairci de 50% vers bg_mid
    text_tertiary = _rgb_to_hex(_blend_rgb(tp_rgb, c[2], 0.50))
    # accent_3 = accent_1 éclairci de 30% vers blanc
    accent_3 = _rgb_to_hex(_blend_rgb(a1_rgb, [255, 255, 255], 0.30))

    return {
        "name": "Colormind 🎨",
        "bg_start": bg_start,
        "bg_mid": bg_mid,
        "bg_end": bg_end,
        "band_top": band_top,
        "band_bottom": band_bottom,
        "text_primary": text_primary,
        "text_secondary": text_secondary,
        "text_tertiary": text_tertiary,
        "accent_1": accent_1,
        "accent_2": accent_2,
        "accent_3": accent_3,
        "photo_border": "#ffffff",
        "deco_line": deco_line,
        "desaturation": 10,
        # Métadonnées Colormind brutes (pour debug)
        "_colormind_raw": [c for c in palette_rgb],
    }


def extract_palette(
    photo_scores: List[Tuple[str, float, Dict[str, float]]],
    n_samples: int = 5,
) -> Dict[str, Any]:
    """Extrait une palette de couleurs depuis les meilleures photos.

    Appelle l'API Colormind avec la couleur moyenne de chaque photo
    comme hint.  En cas d'échec, fallback sur la palette Soleil.

    Args:
        photo_scores: liste de (path, score, details) triée par score décroissant.
        n_samples: nombre de photos à échantillonner (max 5).

    Returns:
        dict palette compatible avec generate_dynamic_css() et config.py.
    """
    top_photos = photo_scores[:n_samples]

    # Extraire les couleurs dominantes comme hints
    hints: List[Any] = []
    for path, score, details in top_photos:
        avg = _get_average_color(path)
        if avg is not None:
            hints.append(avg)
        else:
            hints.append("N")

    # Appeler Colormind
    try:
        palette_rgb = _call_colormind(hints)
        palette = _map_colormind_to_css(palette_rgb)
        return palette
    except Exception as exc:
        print(f"   ⚠️  Colormind indisponible ({exc}) → fallback palette Soleil")
        return _fallback_palette()


# ── Génération CSS dynamique ─────────────────────────────────────────
# Substitution des couleurs de la palette Soleil par celles de la
# palette extraite.  On remplace chaque couleur hex de Soleil par
# l'équivalent de la nouvelle palette.

_SOLEIL_TO_PALETTE_KEY = {
    "#fefcf5": "bg_start",
    "#f5ede0": "bg_mid",
    "#e8cfa0": "bg_end",
    "#8a6a3a": "band_top",       # aussi text_tertiary
    "#c49a5a": "band_bottom",    # aussi accent_1, deco_line
    "#3a2a1a": "text_primary",
    "#5a3a1a": "text_secondary",
    "#d4b888": "accent_3",
    # rgba avec opacité — les couleurs sont les mêmes
    "rgba(254,252,245,": "rgba_bg_start",
    "rgba(196,154,90,": "rgba_band_bottom",
}

# Certaines couleurs Soleil partagent la même clé palette.
# On ajoute des alias pour les cas où la clé de mapping ci-dessus
# ne correspond pas exactement à l'usage voulu.
_SOLEIL_ALIASES = {
    # band_top est aussi utilisé comme text_tertiary
    # band_bottom est aussi accent_1 et deco_line
}


def generate_dynamic_css(palette: Dict[str, Any]) -> str:
    """Génère le CSS dynamique à partir d'une palette.

    Lit le fichier styles/album.css et remplace toutes les couleurs
    de la palette Soleil par celles de la palette fournie.

    Args:
        palette: dict palette (même format que PALETTES_DISPONIBLES["Soleil"]).

    Returns:
        Chaîne CSS avec les couleurs substituées.
    """
    css = _load_soleil_css()
    return _apply_palette_colors(css, palette)


def _load_soleil_css() -> str:
    """Charge le CSS Soleil de référence."""
    from pathlib import Path as _Path
    css_path = _Path(__file__).parent.parent / "styles" / "album.css"
    return css_path.read_text(encoding="utf-8")


def _build_substitution_map(palette: Dict[str, Any]) -> Dict[str, str]:
    """Construit le dictionnaire de substitution Soleil → palette.

    Returns:
        dict: {couleur_soleil: couleur_palette} pour toutes les couleurs.
    """
    subs = {}

    # 1. Mapping principal : hex Soleil → clé palette
    for soleil_hex, key in _SOLEIL_TO_PALETTE_KEY.items():
        if soleil_hex.startswith("rgba"):
            hex_val = palette.get(key.replace("rgba_", ""), "")
            if hex_val:
                r, g, b = _hex_to_rgb(hex_val)
                subs[soleil_hex] = f"rgba({r},{g},{b},"
            continue

        new_val = palette.get(key, "")
        if new_val and new_val.lower() != soleil_hex.lower():
            subs[soleil_hex] = new_val

    return subs


def apply_palette_to_html(html: str, palette: Dict[str, Any]) -> str:
    """Applique la palette de couleurs à un HTML (styles inline)."""
    subs = _build_substitution_map(palette)
    result = html
    for old, new in subs.items():
        result = result.replace(old, new)
    return result


def _apply_palette_colors(text: str, palette: Dict[str, Any]) -> str:
    """Applique les substitutions de couleurs à une chaîne (CSS ou HTML)."""
    subs = _build_substitution_map(palette)
    result = text
    for old, new in subs.items():
        result = result.replace(old, new)
    return result
